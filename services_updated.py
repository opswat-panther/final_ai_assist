import os
import re
import time
from typing import Optional, Set, Dict, Any

from openai import OpenAI, APIError, AuthenticationError

# --- CONFIGURATION ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")

# Run-level tuning (these are safe defaults for KB-style assistants)
RUN_TEMPERATURE_KNOWLEDGE = float(os.environ.get("RUN_TEMPERATURE_KNOWLEDGE", "0.2"))
RUN_TEMPERATURE_CODE = float(os.environ.get("RUN_TEMPERATURE_CODE", "0.4"))

# Guardrails
ENABLE_PRODUCT_SCOPE_GUARDRAIL = os.environ.get("ENABLE_PRODUCT_SCOPE_GUARDRAIL", "1") == "1"
ENABLE_FORMAT_GUARDRAIL = os.environ.get("ENABLE_FORMAT_GUARDRAIL", "1") == "1"
MAX_REWRITE_ATTEMPTS = int(os.environ.get("MAX_REWRITE_ATTEMPTS", "1"))

# Polling safety (only used in fallback poll implementation)
RUN_POLL_INTERVAL_S = float(os.environ.get("RUN_POLL_INTERVAL_S", "0.8"))
RUN_TIMEOUT_S = float(os.environ.get("RUN_TIMEOUT_S", "60"))

# -----------------------------------------------------------------------------
# SYSTEM INSTRUCTIONS (stronger: no-guessing + product scoping + markdown format)
# -----------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """You are the OPSWAT Knowledge Assistant.

Non-negotiables:
1) Do NOT guess. If the knowledge base context does not explicitly contain the needed fact (exact path/endpoint/flag/value), say:
   "Not found in the provided knowledge base." Then ask for version/OS/product and suggest where to look in the product UI/docs.
2) Stay product-scoped. Only talk about the product(s) mentioned in the user’s question (Core vs Kiosk vs ICAP vs Cloud, etc).
   If retrieved context mentions a different product, ignore it.
3) Output MUST be clean Markdown and structured:

## Answer
(1–2 sentences, direct)

## Steps / Example
- Use numbered steps or bullets.
- Put endpoints/paths/JSON/commands in code fences.

## Notes (optional)
- Version/OS-specific notes.

## Sources
- List doc names / sections used. If no sources were used, say so.

Intent handling:
- KNOWLEDGE: Provide a direct factual answer grounded in KB. Prefer exact strings for paths/endpoints/flags/ports.
- CODE: Provide a minimal working template/example immediately (with placeholders), THEN ask up to 2 clarifying questions.
- PRIVATE/SECURITY-BYPASS: Refuse briefly and offer safe alternatives (official docs/support/IT process).
- CONTEXT: Answer using only chat history; if insufficient, provide a generic example without inventing product facts.

Style:
- No repeating the user’s question.
- No filler.
- Keep it clear and step-by-step.
"""

# -----------------------------------------------------------------------------
# Heuristics for intent + scoping (used to set temperature + add guardrails)
# -----------------------------------------------------------------------------
_PRODUCT_KEYWORDS: Dict[str, Set[str]] = {
    "MetaDefender Core": {"metadefender core", "md core", "core"},
    "MetaDefender Kiosk": {"metadefender kiosk", "kiosk"},
    "MetaDefender ICAP": {"metadefender icap", "icap"},
    "MetaDefender Cloud": {"metadefender cloud", "md cloud", "cloud"},
    "OESIS": {"oesis", "endpoint security", "opwat endpoint", "device security"},
}

_CODE_HINTS = {
    "code", "snippet", "example", "sample", "implement", "implementation", "sdk",
    "curl", "http", "endpoint", "api", "json", "yaml", "values.yaml", "dockerfile",
    "python", "c#", "csharp", "java", "javascript", "node", "dotnet", "powershell",
}

_PRIVATE_HINTS = {
    "bypass", "exploit", "crack", "pirate", "steal", "leak", "private key", "api key",
    "password", "credential", "disable security", "evade", "backdoor",
}

_CONTEXT_HINTS = {
    "based on our chat", "as we discussed", "earlier you said", "in this conversation",
    "previous message", "last time",
}

_EXACT_FACT_HINTS = {
    "exact", "full path", "path", "endpoint", "url", "health", "status api", "port",
    "flag", "parameter name", "config file location", "values.yaml",
}

_REQUIRED_HEADINGS = ["## Answer", "## Steps / Example", "## Sources"]


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def detect_products(text: str) -> Set[str]:
    t = _normalize(text)
    found: Set[str] = set()
    for product, keys in _PRODUCT_KEYWORDS.items():
        if any(k in t for k in keys):
            found.add(product)
    return found


def categorize_intent(user_message: str, *, product_hint: Optional[str] = None, language_hint: Optional[str] = None) -> str:
    t = _normalize(user_message)
    if any(h in t for h in _PRIVATE_HINTS):
        return "PRIVATE"
    if any(h in t for h in _CONTEXT_HINTS):
        return "CONTEXT"
    if language_hint and language_hint.strip():
        return "CODE"
    if any(h in t for h in _CODE_HINTS):
        return "CODE"
    return "KNOWLEDGE"


def needs_exact_fact(user_message: str) -> bool:
    t = _normalize(user_message)
    return any(h in t for h in _EXACT_FACT_HINTS)


def build_wrapped_user_message(
    user_message: str,
    *,
    product_hint: Optional[str] = None,
    language_hint: Optional[str] = None,
    task_hint: Optional[str] = None,
) -> str:
    # Determine scope based on question + optional hints
    q_products = detect_products(user_message)
    if product_hint:
        q_products.add(product_hint.strip())

    scope_line = ""
    if q_products:
        scope_line = f"Scope: {', '.join(sorted(q_products))}. Do not mention other OPSWAT products."

    intent = categorize_intent(user_message, product_hint=product_hint, language_hint=language_hint)

    exact_line = ""
    if needs_exact_fact(user_message):
        exact_line = (
            'This question requires exact values (endpoints/paths/flags/ports). '
            'Do NOT invent. If not present in the KB context, reply with: "Not found in the provided knowledge base."'
        )

    code_line = ""
    if intent == "CODE":
        hints = []
        if product_hint:
            hints.append(f"Product: {product_hint}")
        if language_hint:
            hints.append(f"Language: {language_hint}")
        if task_hint:
            hints.append(f"Task: {task_hint}")
        hint_block = ("\n".join(f"- {h}" for h in hints)) if hints else "- (no extra hints provided)"
        code_line = (
            "This is a CODE request.\n"
            "Provide a minimal working template immediately (with placeholders), then ask at most 2 clarifying questions.\n"
            "Known hints:\n"
            f"{hint_block}"
        )

    format_line = (
        "Output format (strict):\n"
        "## Answer\n"
        "## Steps / Example\n"
        "## Notes (optional)\n"
        "## Sources\n"
    )

    parts = [
        "You are responding to an end-user question.",
        scope_line,
        exact_line,
        code_line,
        format_line,
        "User question:\n" + user_message.strip(),
    ]
    return "\n\n".join([p for p in parts if p])


# -----------------------------------------------------------------------------
# OpenAI client init
# -----------------------------------------------------------------------------
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY is missing.")

client = OpenAI(api_key=OPENAI_API_KEY)


class ThreadManager:
    """Manages conversation threads (in-memory). Replace with Redis/Postgres in production."""
    def __init__(self):
        self.threads: Dict[str, str] = {}

    def get_or_create_thread(self, user_id: str) -> str:
        if user_id in self.threads:
            return self.threads[user_id]

        print(f"Creating new thread for user: {user_id}")
        thread = client.beta.threads.create()
        self.threads[user_id] = thread.id
        return thread.id

    def delete_thread(self, user_id: str, thread_id: Optional[str] = None) -> bool:
        """
        Deletes the stored thread mapping.

        If thread_id is provided, it must match the stored thread_id for that user.
        """
        if user_id not in self.threads:
            return False

        if thread_id and self.threads[user_id] != thread_id:
            return False

        del self.threads[user_id]
        return True


# Singleton instance
thread_manager = ThreadManager()


def _create_and_poll_run(thread_id: str, *, temperature: float) -> Any:
    """
    Prefer SDK helper create_and_poll when available.
    Fallback to manual polling for compatibility.
    """
    run_kwargs: Dict[str, Any] = {
        "thread_id": thread_id,
        "assistant_id": ASSISTANT_ID,
        "instructions": SYSTEM_INSTRUCTION,
        "temperature": temperature,
    }

    # 1) Preferred path: create_and_poll
    try:
        return client.beta.threads.runs.create_and_poll(**run_kwargs)
    except TypeError:
        # Some SDK versions may not accept temperature/instructions here.
        run_kwargs.pop("temperature", None)
        try:
            return client.beta.threads.runs.create_and_poll(**run_kwargs)
        except Exception:
            pass  # fall through to manual polling
    except AttributeError:
        pass  # SDK doesn't have create_and_poll

    # 2) Manual polling fallback
    run_kwargs_create = dict(run_kwargs)
    # create() may also reject temperature/instructions depending on SDK/version
    try:
        run = client.beta.threads.runs.create(**run_kwargs_create)
    except TypeError:
        run_kwargs_create.pop("temperature", None)
        run_kwargs_create.pop("instructions", None)
        run = client.beta.threads.runs.create(**run_kwargs_create)

    start = time.time()
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run.status in {"completed", "failed", "cancelled", "expired", "requires_action"}:
            return run
        if time.time() - start > RUN_TIMEOUT_S:
            raise TimeoutError(f"Assistant run timed out after {RUN_TIMEOUT_S} seconds.")
        time.sleep(RUN_POLL_INTERVAL_S)


def _get_latest_assistant_text(thread_id: str) -> str:
    messages = client.beta.threads.messages.list(thread_id=thread_id, order="desc")
    for msg in messages.data:
        if msg.role == "assistant":
            if msg.content and hasattr(msg.content[0], "text"):
                return msg.content[0].text.value
    return "Error: Assistant completed run but returned no text."


def _has_required_markdown_structure(text: str) -> bool:
    if not text:
        return False
    return all(h in text for h in _REQUIRED_HEADINGS)


def _enforce_product_scope(question: str, answer: str) -> bool:
    q_prod = detect_products(question)
    a_prod = detect_products(answer)
    if not q_prod:
        return True  # user was vague; don't block
    return a_prod.issubset(q_prod)


def get_assistant_response(
    thread_id: str,
    user_message: str,
    *,
    product_hint: Optional[str] = None,
    language_hint: Optional[str] = None,
    task_hint: Optional[str] = None,
) -> str:
    """Sends a message to the Assistant and waits for the response."""
    if not ASSISTANT_ID:
        raise ValueError("ASSISTANT_ID is not set in environment variables.")

    intent = categorize_intent(user_message, product_hint=product_hint, language_hint=language_hint)
    temperature = RUN_TEMPERATURE_CODE if intent == "CODE" else RUN_TEMPERATURE_KNOWLEDGE

    wrapped = build_wrapped_user_message(
        user_message,
        product_hint=product_hint,
        language_hint=language_hint,
        task_hint=task_hint,
    )

    # 1) Add (wrapped) user message to thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=wrapped,
    )

    # 2) Run assistant
    run = _create_and_poll_run(thread_id, temperature=temperature)

    if run.status != "completed":
        error_msg = run.last_error.message if getattr(run, "last_error", None) else run.status
        raise Exception(f"Assistant run failed: {error_msg}")

    # 3) Read response
    answer = _get_latest_assistant_text(thread_id)

    # 4) Optional rewrite guardrails (single retry)
    rewrite_attempts = 0
    while rewrite_attempts < MAX_REWRITE_ATTEMPTS:
        needs_rewrite = False

        if ENABLE_FORMAT_GUARDRAIL and not _has_required_markdown_structure(answer):
            needs_rewrite = True

        if ENABLE_PRODUCT_SCOPE_GUARDRAIL and not _enforce_product_scope(user_message, answer):
            needs_rewrite = True

        if not needs_rewrite:
            break

        rewrite_attempts += 1
        q_prod = detect_products(user_message)
        a_prod = detect_products(answer)
        extras = sorted(a_prod - q_prod)

        rewrite_prompt = (
            "Rewrite your previous answer with these constraints:\n"
            "- Use the strict Markdown structure (## Answer, ## Steps / Example, ## Notes (optional), ## Sources).\n"
            "- Do NOT guess. If an exact endpoint/path/flag/value is not in the KB context, say: \"Not found in the provided knowledge base.\"\n"
        )
        if q_prod:
            rewrite_prompt += f"- ONLY discuss: {', '.join(sorted(q_prod))}.\n"
        if extras:
            rewrite_prompt += f"- Remove references to: {', '.join(extras)}.\n"

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=rewrite_prompt,
        )

        run = _create_and_poll_run(thread_id, temperature=temperature)
        if run.status != "completed":
            break
        answer = _get_latest_assistant_text(thread_id)

    return answer
