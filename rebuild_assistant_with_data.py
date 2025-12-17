import os
import glob
from openai import OpenAI

# --- CONFIGURATION ---
# Ensure your new API Key is set in your environment
API_KEY = os.environ.get("OPENAI_API_KEY")
DOCS_FOLDER = "knowledge_base"  # <--- Put your files in this folder

# System Instructions (Same as before)
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
    "    * **IF KNOWLEDGE:** Provide a direct, factual answer using the attached knowledge base."
)


def rebuild_assistant():
    if not API_KEY:
        print("❌ CRITICAL ERROR: OPENAI_API_KEY is missing.")
        return

    client = OpenAI(api_key=API_KEY)

    # 1. Create a Vector Store (The "Brain" for your files)
    print(f"--- 1. Creating Vector Store ---")
    vector_store = client.beta.vector_stores.create(name="OPSWAT Knowledge Store")
    print(f"✅ Vector Store Created: {vector_store.id}")

    # 2. Find and Upload Files
    print(f"--- 2. Uploading Files from '{DOCS_FOLDER}' ---")

    # Get all *files* in the folder (skip subdirectories like 'model data')
    file_paths = [
        path
        for path in glob.glob(os.path.join(DOCS_FOLDER, "*"))
        if os.path.isfile(path)
    ]

    if not file_paths:
        print(f"⚠️ WARNING: No files found in {DOCS_FOLDER}. Assistant will have NO knowledge.")
    else:
        # Open files as binary streams
        file_streams = [open(path, "rb") for path in file_paths]

        try:
            # Use the helper to upload and poll status automatically
            file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store.id,
                files=file_streams,
            )
        finally:
            # Always close file handles
            for f in file_streams:
                f.close()

        print(f"✅ Uploaded {len(file_paths)} files. Status: {file_batch.status}")
        print(f"   File Counts: {file_batch.file_counts}")

    # 3. Create the Assistant with the Vector Store
    print(f"--- 3. Creating Assistant ---")
    assistant = client.beta.assistants.create(
        name="OPSWAT Knowledge Assistant (Rebuilt)",
        instructions=SYSTEM_INSTRUCTION,
        model="gpt-4.1-mini",  # or your preferred model
        tools=[{"type": "file_search"}],
        tool_resources={
            "file_search": {
                "vector_store_ids": [vector_store.id]
            }
        },
    )

    print("\n" + "=" * 60)
    print("✅ REBUILD COMPLETE")
    print("=" * 60)
    print(f"NEW ASSISTANT ID: {assistant.id}")
    print("=" * 60)
    print("👉 ACTION: Update your 'docker-compose.yml' with this new ID.")


if __name__ == "__main__":
    # Create the folder if it doesn't exist, just to be safe
    if not os.path.exists(DOCS_FOLDER):
        os.makedirs(DOCS_FOLDER)
        print(f"📁 Created folder '{DOCS_FOLDER}'. Please put your documents in there and re-run.")
    else:
        rebuild_assistant()
