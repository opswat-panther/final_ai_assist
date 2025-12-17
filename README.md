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

⚙️ Configuration
The application is controlled by environment variables. You must set these before running the code.

Variable,Required?,Description
OPENAI_API_KEY,Yes,Your OpenAI API secret key.
ASSISTANT_ID,Yes,The ID of the specific assistant to query.
FLASK_DEBUG,No,"Set to 1 for debug mode, 0 for production."
ENABLE_PRODUCT_SCOPE_GUARDRAIL,No,Set to 1 (default) to restrict answers to specific products.

▶️ How to Run
1. Start the Server (app_updated.py)
Mac / Linux:

export OPENAI_API_KEY="sk-YOUR_KEY_HERE"
export ASSISTANT_ID="asst-YOUR_ID_HERE"
python app_updated.py

Windows (Command Prompt):
set OPENAI_API_KEY=sk-YOUR_KEY_HERE
set ASSISTANT_ID=asst-YOUR_ID_HERE
python app_updated.py

You should see output indicating the server is running on http://127.0.0.1:5000.

2. Use the Chat Interface
Once the server is running, open your web browser and go to: http://127.0.0.1:5000
🧪 Automated Testing
The auto_evaluator.py script sends the questions from test_questions.csv to your running local API and generates an Excel report with grades.

Note: The main app (app_updated.py) must be running in a separate terminal window first.

Run the Evaluator:
# Ensure OPENAI_API_KEY is set in this terminal as well
python auto_evaluator.py

Output:

Console logs showing the score for each question.

A generated file: evaluation_report_pro.xlsx.

🐳 Docker Deployment
To deploy using Docker, ensure all files are in the same directory.

Dockerfile Example:
FROM python:3.9-slim
WORKDIR /app
COPY . /app
RUN pip install flask flask-cors openai pydantic pandas requests openpyxl
CMD ["python", "app_updated.py"]
