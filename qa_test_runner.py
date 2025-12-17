import requests
import json
import uuid
import time
from sys import exit

# --- Configuration ---
# The OPSWAT Assistant (Flask) runs on port 5000
ASSISTANT_URL = "http://127.0.0.1:5000/chat"
# The QA Scorer (Node.js) runs on port 8787
CRITIQUE_URL = "http://127.0.0.1:8787/api/critique"

# For the Flask app, we need a persistent user ID and a thread ID
# Use a random ID for this session
TEST_USER_ID = str(uuid.uuid4())
current_thread_id = None 

def fetch_assistant_response(question, user_id, thread_id):
    """
    Step 1: Calls the Flask Assistant API to get the answer.
    """
    global current_thread_id

    payload = {
        "user_id": user_id,
        "message": question,
        "thread_id": thread_id
    }
    
    print(f"\n--- 1. Sending Question to Assistant ({ASSISTANT_URL}) ---")
    
    try:
        response = requests.post(ASSISTANT_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Update the thread ID for the next turn
        current_thread_id = data.get('thread_id')

        print(f"   [INFO] Thread ID: {current_thread_id}")
        return data.get('response', 'Error: No response text found.'), current_thread_id

    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to the Assistant server at {ASSISTANT_URL}.")
        print("        Ensure 'app.py' is running in a separate terminal.")
        exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Assistant API request failed: {e}")
        print(f"        Response status: {response.status_code}")
        print(f"        Response content: {response.text}")
        exit(1)


def fetch_critique(question, answer):
    """
    Step 2: Calls the Node.js QA Scorer API to get the critique.
    """
    payload = {
        "question": question,
        "answer": answer
    }

    print(f"\n--- 2. Sending Q/A to Scorer ({CRITIQUE_URL}) ---")
    
    try:
        response = requests.post(CRITIQUE_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # The critique is expected to be in data.choices[0].message.content (OpenAI format)
        critique_text = data.get('choices', [{}])[0].get('message', {}).get('content', 'CRITIQUE FAILED: Missing critique text.')
        
        if response.status_code != 200 or 'CRITIQUE FAILED' in critique_text:
            # Check for specific server-side errors
            error_message = data.get('error', {}).get('message', 'Unknown Error')
            if 'OPENAI_API_KEY' in error_message:
                print("\n[CRITICAL ERROR] The Node.js scorer server is missing the OPENAI_API_KEY.")
                print("                 Please set the environment variable and restart the Node server.")
                exit(1)
                
        return critique_text

    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to the Scorer server at {CRITIQUE_URL}.")
        print("        Ensure 'qa_critique_api.js' is running in a separate terminal.")
        exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Scorer API request failed: {e}")
        print(f"        Response status: {response.status_code}")
        print(f"        Response content: {response.text}")
        exit(1)


def main():
    print("=" * 60)
    print("OPSWAT QA SIMULATOR (Assistant + Scorer Integration)")
    print(f"Test Session User ID: {TEST_USER_ID[:8]}...")
    print("=" * 60)
    
    while True:
        try:
            # Get Question from user
            question = input("\nEnter Question (or 'quit' to exit): \n> ")
            if question.lower() == 'quit':
                break
            if not question.strip():
                continue

            # STEP 1: Get Answer from Flask Assistant
            assistant_answer, thread_id = fetch_assistant_response(question, TEST_USER_ID, current_thread_id)
            
            # Print the immediate answer
            print("\n" + "="*20 + " ASSISTANT ANSWER " + "="*20)
            print(assistant_answer)
            
            # STEP 2: Get Critique from Node.js Scorer
            critique = fetch_critique(question, assistant_answer)

            # Print the final critique
            print("\n" + "="*22 + " QA CRITIQUE " + "="*23)
            print(critique)
            print("=" * 57 + "\n")

        except KeyboardInterrupt:
            print("\nExiting simulator.")
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            break

if __name__ == "__main__":
    # Check for required library before running
    try:
        import requests
    except ImportError:
        print("\n[SETUP ERROR] The 'requests' library is required to run this script.")
        print("Please install it using: 'pip install requests'")
        exit(1)
    
    main()