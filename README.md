# OPSWAT Knowledge Assistant

This project is a Flask-based API wrapper for a custom OpenAI Assistant. It serves as a backend to answer technical support questions regarding OPSWAT products, complete with a web-based testing UI and an automated evaluation script.

## 📂 Project Structure

| File Name | Description |
| :--- | :--- |
| **`app_updated.py`** | **Entry Point**. The Flask server file. It defines API routes (`/chat`, `/health`) and serves the UI. |
| **`services_updated.py`** | **Logic Layer**. Handles OpenAI Assistant interaction, thread management, and guardrails (formatting/scoping). |
| **`models_updated.py`** | **Validation**. Pydantic data models used to validate incoming API requests and define strict types. |
| **`opswat_assistant_ui.html`** | **Frontend**. A simple HTML/JS interface to chat with the assistant locally in your browser. |
| **`auto_evaluator.py`** | **QA Tool**. A script that runs questions from `test_questions.csv` against the API and grades them using GPT-4o. |
| **`test_questions.csv`** | **Dataset**. A list of technical questions used by the auto-evaluator to test performance. |

---

## 🚀 Setup & Installation

### 1. Prerequisites
* Python 3.9 or higher.
* An OpenAI API Key (`sk-...`).
* An OpenAI Assistant ID (`asst-...`) created in the OpenAI platform.

### 2. Install Dependencies
Open your terminal in the project folder and run:

```bash
pip install flask flask-cors openai pydantic pandas requests openpyxl
