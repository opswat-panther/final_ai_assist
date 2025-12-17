import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from models import ChatRequest, ThreadDeleteRequest, ValidationError
from services import (
    thread_manager,
    get_assistant_response,
    ASSISTANT_ID,
    APIError,
    AuthenticationError,
)

# --- FLASK SETUP ---
app = Flask(__name__)
CORS(app)


# --- ROOT ROUTE (serves UI) ---
@app.route("/", methods=["GET"])
def index():
    """
    Serves the frontend UI file.

    Note: Ensure opswat_assistant_ui.html is in the same folder as app.py inside your Docker image.
    """
    try:
        return send_file("opswat_assistant_ui.html")
    except FileNotFoundError:
        return (
            "Error: opswat_assistant_ui.html not found. Please ensure it is in the same folder as app.py",
            404,
        )


@app.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint."""
    return (
        jsonify(
            {
                "status": "ok",
                "service": "opswat-assistant-api",
                "assistant_id": ASSISTANT_ID,
            }
        ),
        200,
    )


@app.route("/thread/delete", methods=["POST"])
def delete_thread_endpoint():
    """
    Deletes a conversation thread mapping for a given user.

    This removes the server-side mapping (in-memory by default). It does NOT delete data in OpenAI.
    """
    try:
        data = ThreadDeleteRequest(**(request.get_json() or {}))
    except ValidationError as e:
        return jsonify({"error": "Invalid input format for deletion.", "details": e.errors()}), 400
    except Exception:
        return jsonify({"error": "Invalid JSON payload."}), 400

    user_id = data.user_id
    thread_id = data.thread_id

    try:
        success = thread_manager.delete_thread(user_id=user_id, thread_id=thread_id)
        if success:
            return jsonify({"message": f"Thread {thread_id} deleted successfully.", "deleted": True}), 200
        return (
            jsonify(
                {
                    "message": f"Thread {thread_id} not found for user {user_id}.",
                    "deleted": False,
                }
            ),
            404,
        )
    except Exception as e:
        return jsonify({"error": f"Failed to delete thread: {str(e)}"}), 500


@app.route("/chat", methods=["POST"])
def chat():
    """Handles incoming chat messages, validates data, and returns assistant response."""
    # 1) Input Validation
    try:
        data = ChatRequest(**(request.get_json() or {}))
    except ValidationError as e:
        return jsonify({"error": "Invalid input format.", "details": e.errors()}), 400
    except Exception:
        return jsonify({"error": "Invalid JSON payload."}), 400

    user_id = data.user_id
    message = data.message

    # Optional hints (do not break older clients)
    product_hint = getattr(data, "product", None)
    language_hint = getattr(data, "language", None)
    task_hint = getattr(data, "task", None)

    # 2) Determine/Create Thread ID
    try:
        thread_id = data.thread_id or thread_manager.get_or_create_thread(user_id)
    except AuthenticationError as e:
        return jsonify({"error": str(e)}), 401
    except APIError as e:
        status_code = getattr(e, "status_code", 500)
        return jsonify({"error": str(e)}), status_code
    except Exception as e:
        return jsonify({"error": f"Failed to initialize chat thread: {str(e)}"}), 500

    # 3) Interact with OpenAI Assistant
    try:
        response_text = get_assistant_response(
            thread_id=thread_id,
            user_message=message,
            product_hint=product_hint,
            language_hint=language_hint,
            task_hint=task_hint,
        )

        return jsonify({"response": response_text, "thread_id": thread_id, "user_id": user_id}), 200

    except AuthenticationError as e:
        return jsonify({"error": str(e)}), 401
    except APIError as e:
        status_code = getattr(e, "status_code", 500)
        return jsonify({"error": str(e)}), status_code
    except Exception as e:
        return (
            jsonify(
                {
                    "error": str(e),
                    "message": "An unexpected server error occurred during the assistant run.",
                }
            ),
            500,
        )


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", "5000"))
    print(f"Assistant ID: {ASSISTANT_ID}")
    app.run(debug=debug, port=port, host="0.0.0.0")
