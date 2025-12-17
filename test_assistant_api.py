import requests
import json
import uuid
import time

# --- Configuration ---
API_BASE_URL = "http://127.0.0.1:5000"
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"
DELETE_ENDPOINT = f"{API_BASE_URL}/thread/delete"
TEST_USER_ID = str(uuid.uuid4()) # Unique user ID for testing

# --- Helpers ---
def print_status(message, is_success):
    """Prints a formatted success or failure message."""
    color = "\033[92m[SUCCESS]\033[0m" if is_success else "\033[91m[FAILURE]\033[0m"
    print(f"{color} {message}")

def run_test(name, func):
    """Wrapper to run a test function and handle exceptions."""
    print(f"\n--- Running Test: {name} ---")
    try:
        start_time = time.time()
        result = func()
        end_time = time.time()
        
        if result is True:
            print_status(f"{name} completed successfully in {end_time - start_time:.2f}s", True)
        elif result is False:
             # If the function returned False, it's an intended failure from the test logic
             print_status(f"{name} failed assertion.", False)
        else:
            print_status(f"{name} returned unexpected result: {result}", False)

        return result

    except requests.exceptions.ConnectionError:
        print_status(f"{name} failed. Server not running at {API_BASE_URL}. Please start 'python app.py'.", False)
        return False
    except AssertionError as e:
        print_status(f"{name} failed assertion: {e}", False)
        return False
    except Exception as e:
        print_status(f"{name} failed with unhandled exception: {e}", False)
        return False

# --- Test Functions ---

def test_01_health_check():
    """Tests the /health endpoint."""
    response = requests.get(HEALTH_ENDPOINT)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert data.get('status') == 'ok', "Health status is not 'ok'"
    assert 'assistant_id' in data, "Missing 'assistant_id' in response"
    
    return True

def test_02_new_thread_creation():
    """Tests /chat by creating a new thread (no thread_id sent)."""
    global created_thread_id
    
    payload = {
        "user_id": TEST_USER_ID,
        "message": "What is the purpose of MetaDefender Core?"
    }
    
    response = requests.post(CHAT_ENDPOINT, json=payload)
    
    assert response.status_code == 200, f"Expected 200 for new chat, got {response.status_code}"
    data = response.json()
    
    # 1. Check for a new thread_id
    new_thread_id = data.get('thread_id')
    assert new_thread_id is not None and len(new_thread_id) > 10, "Did not receive a valid new thread_id"
    
    # 2. Check for a response (The actual content is less important than its existence)
    assert isinstance(data.get('response'), str) and len(data['response']) > 50, "Did not receive a substantial response"
    
    # Store the thread ID for the next tests
    created_thread_id = new_thread_id
    
    print(f"Created Thread ID: {created_thread_id}")
    return True

def test_03_thread_continuation():
    """Tests /chat by continuing the conversation with the created thread_id."""
    # Ensure the ID from the previous test is available
    if not created_thread_id:
        print_status("Skipped: Thread ID not set from previous test.", False)
        return False

    # Ask a question that relies on the Assistant's system instruction policy (CODE)
    payload = {
        "user_id": TEST_USER_ID,
        "message": "I need a Python snippet to call the multiscanning API."
    }
    
    response = requests.post(CHAT_ENDPOINT, json=payload)
    
    assert response.status_code == 200, f"Expected 200 for continued chat, got {response.status_code}"
    data = response.json()
    
    # Check that the thread ID is the same
    assert data.get('thread_id') == created_thread_id, "Thread ID changed during continuation"
    
    # Check that the response indicates the policy is working (prompting for details)
    response_text = data.get('response', '')
    assert 'programming language' in response_text or 'product/API' in response_text, "Policy check (CODE intent) seems to have failed."
    
    return True

def test_04_input_validation():
    """Tests Pydantic validation (400 response) by sending an invalid payload."""
    payload_missing_user = {
        # "user_id": TEST_USER_ID, # Missing user_id
        "message": "This is a test of missing data."
    }
    
    response = requests.post(CHAT_ENDPOINT, json=payload_missing_user)
    
    assert response.status_code == 400, f"Expected 400 validation error, got {response.status_code}"
    data = response.json()
    
    assert 'Invalid input format' in data.get('error', ''), "Did not receive expected validation error message"
    assert 'details' in data, "Missing 'details' array with validation errors"
    
    return True

def test_05_thread_deletion():
    """Tests the /thread/delete endpoint and verifies idempotency (i.e., deleting an already deleted thread)."""
    if not created_thread_id:
        print_status("Skipped: Thread ID not set from previous test.", False)
        return False
        
    payload = {
        "user_id": TEST_USER_ID,
        "thread_id": created_thread_id
    }
    
    # 1. First Deletion Attempt (Expected Success)
    response = requests.post(DELETE_ENDPOINT, json=payload)
    assert response.status_code == 200, f"Expected 200 for successful deletion, got {response.status_code}"
    data = response.json()
    assert data.get('deleted') is True, "First deletion response indicated failure"
    
    print(f"Thread {created_thread_id} successfully deleted on first attempt.")

    # 2. Second Deletion Attempt (Testing Idempotency / Already Deleted State)
    # Since the thread is deleted from the local store, the server should return 404.
    second_response = requests.post(DELETE_ENDPOINT, json=payload)
    
    # Check for the 404 status code (Not Found in local store)
    assert second_response.status_code == 404, f"Expected 404 (already deleted) on second attempt, got {second_response.status_code}"
    data_second = second_response.json()
    
    # Check that the deleted flag is correctly set to False
    assert data_second.get('deleted') is False, "Second deletion response should show 'deleted: False'"
    
    return True

# --- Main Test Execution ---

if __name__ == "__main__":
    
    created_thread_id = None
    
    # List of tests to run in order
    tests = [
        test_01_health_check,
        test_02_new_thread_creation,
        test_03_thread_continuation,
        test_04_input_validation,
        test_05_thread_deletion,
    ]
    
    success_count = 0
    
    # Attempt to ping the server first
    try:
        requests.get(HEALTH_ENDPOINT, timeout=5)
        print("API server is accessible. Starting tests...")
    except requests.exceptions.ConnectionError:
        print("\n\033[91m[CRITICAL]\033[0m API server is NOT running. Please start it using 'python app.py' and try again.")
        exit(1)


    for test in tests:
        if run_test(test.__name__, test):
            success_count += 1

    print("\n" + "="*50)
    print(f"TEST SUMMARY: {success_count} / {len(tests)} tests passed.")
    print("="*50)
