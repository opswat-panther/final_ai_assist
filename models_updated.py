from pydantic import BaseModel, ValidationError


class ChatRequest(BaseModel):
    """
    Defines the expected structure for incoming chat requests.

    Backwards-compatible: older clients can keep sending only user_id/message/thread_id.
    New optional fields help the assistant answer CODE questions with fewer follow-ups.
    """
    user_id: str
    message: str
    thread_id: str | None = None  # optional for the first message

    # Optional hints (safe defaults)
    product: str | None = None    # e.g., "MetaDefender Core"
    language: str | None = None   # e.g., "Python", "C#", "Java"
    task: str | None = None       # e.g., "SDK integration", "ICAP config", "Health endpoint"


class ThreadDeleteRequest(BaseModel):
    """Defines the expected structure for thread deletion requests."""
    user_id: str
    thread_id: str
