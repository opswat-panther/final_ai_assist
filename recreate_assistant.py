import os
from openai import OpenAI

# --- CONFIGURATION ---
# Ensure your new API Key is set in your terminal or paste it here temporarily
API_KEY = os.environ.get("OPENAI_API_KEY") 

# The System Instructions (Copied from your services.py)
SYSTEM_INSTRUCTION = (
    "You are the OPSWAT Knowledge Assistant, a highly professional and policy-driven expert. "
    "Your primary goal is to provide accurate information on OPSWAT products and technologies, "
    "while strictly adhering to the following Query Handling Protocol. Your tone must always be professional, "
    "helpful, and collaborative. \n\n"
    "QUERY HANDLING PROTOCOL:\n"
    "1.  **Intent Categorization:** Before generating a response, determine the query's primary intent "
    "    (KNOWLEDGE, CODE, PRIVATE, CONTEXT).\n"
    "2.  **Policy Enforcement:**\n"
    "    * **IF PRIVATE:** Immediately decline with a professional statement.\n"
    "    * **IF CODE:** Do NOT provide code immediately. Prompt the user for product, language, and task.\n"
    "    * **IF CONTEXT:** Answer based *only* on the chat history.\n"
    "    * **IF KNOWLEDGE:** Provide a direct, factual answer."
)

def create_assistant():
    if not API_KEY:
        print("CRITICAL ERROR: OPENAI_API_KEY is not found in environment variables.")
        return

    client = OpenAI(api_key=API_KEY)

    print("--- Creating New OPSWAT Assistant ---")
    try:
        # Create the assistant with File Search enabled (for knowledge retrieval)
        assistant = client.beta.assistants.create(
            name="OPSWAT Knowledge Assistant (Re-created)",
            instructions=SYSTEM_INSTRUCTION,
            model="gpt-4-turbo", # or "gpt-4o"
            tools=[{"type": "file_search"}] 
        )

        print("\n✅ SUCCESS! Assistant Created.")
        print("="*60)
        print(f"NEW ASSISTANT ID: {assistant.id}")
        print("="*60)
        print("\nACTION REQUIRED: Copy the ID above and paste it into your docker-compose.yml")

    except Exception as e:
        print(f"❌ Failed to create assistant: {e}")

if __name__ == "__main__":
    create_assistant()