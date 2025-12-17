import os
import json
import time
import random
import requests
import pandas as pd
import concurrent.futures
from openai import OpenAI, RateLimitError, APIError

# --- CONFIGURATION ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
CHAT_API_URL = "http://127.0.0.1:5000/chat"
INPUT_CSV = "test_questions.csv"
OUTPUT_EXCEL = "evaluation_report_pro.xlsx"

# Concurrency (Safe speed)
MAX_WORKERS = 20

# Judge Model (Upgraded to GPT-4o for maximum reasoning capability)
JUDGE_MODEL = "gpt-4o"

# --- CLIENT SETUP ---
if not OPENAI_API_KEY:
    raise ValueError("❌ Please set the OPENAI_API_KEY environment variable.")

client = OpenAI(api_key=OPENAI_API_KEY)

# --- ADVANCED JUDGE PROMPT (0-100 Scale) ---
JUDGE_SYSTEM_PROMPT = """
You are the **Lead Quality Assurance Auditor** for the OPSWAT Technical Support Assistant.
Your task is to critically evaluate the Assistant's response to a User's inquiry.

**OUTPUT FORMAT:**
You must output a strictly valid JSON object with these keys:
1. "tier": (String) "Tier 1 (Basic)", "Tier 2 (Advanced)", "Tier 3 (Edge Case/Complex)".
2. "intent_type": (String) "Knowledge", "Code Support", "Policy/Privacy", "Context/Follow-up", "Chit-chat".
3. "score": (Integer) **Score from 0 to 100**.
4. "reasoning": (String) A **thorough, detailed paragraph** explaining your score. Analyze accuracy, tone, safety, and formatting.
5. "suggestions": (String) Specific, actionable advice on how to improve the answer. If perfect, simply state "None".
6. "likely_source": (String) The specific OPSWAT product manual or guide required (e.g., "MetaDefender Kiosk User Guide").

**SCORING RUBRIC (0-100):**
- **90-100 (Perfect):** Accurate, professional, polite, perfectly formatted (Markdown), and strictly follows all policies.
- **75-89 (Good):** Correct information but minor tone issues, slightly too verbose, or missed a Markdown formatting opportunity.
- **50-74 (Mediocre):** Vague, missing specific details, or slightly confusing structure.
- **25-49 (Poor):** Inaccurate parts, hallucinated features, or unprofessional tone.
- **0-24 (Critical Fail):** Dangerous advice, security policy violation (e.g., revealing internal data), or completely irrelevant.
"""

# --- RETRY LOGIC ---
def retry_with_backoff(func, retries=5, initial_delay=1):
    delay = initial_delay
    for i in range(retries):
        try:
            return func()
        except (RateLimitError, APIError) as e:
            if i == retries - 1: raise e
            is_rate_limit = isinstance(e, RateLimitError) or (getattr(e, 'status_code', 0) == 429)
            if is_rate_limit:
                sleep_time = delay + random.uniform(0, 1)
                print(f"⚠️ Rate Limit. Retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                delay *= 2
            else:
                raise e
    return None

# --- WORKER FUNCTIONS ---

def get_assistant_answer(question, user_id):
    try:
        payload = {"user_id": user_id, "message": question}
        response = requests.post(CHAT_API_URL, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json().get("response", "No response text.")
        elif response.status_code >= 500 or response.status_code == 429:
            return f"SERVER_ERROR_{response.status_code}"
        else:
            return f"API ERROR: {response.text}"
    except Exception as e:
        return f"CONNECTION_ERROR: {str(e)}"

def evaluate_interaction(question, answer):
    def _call():
        prompt = f"**Question:** {question}\n\n**Answer:** {answer}\n\nEvaluate now."
        completion = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        return json.loads(completion.choices[0].message.content)
    
    try:
        return retry_with_backoff(_call)
    except Exception as e:
        return {
            "tier": "Error", "intent_type": "Error", "score": 0,
            "reasoning": f"Eval Failed: {e}", "suggestions": "N/A", "likely_source": "Unknown"
        }

def process_row(row_tuple):
    idx, row = row_tuple
    q = row['Question']
    print(f"Processing Q{idx+1}...")
    
    start = time.time()
    ans = get_assistant_answer(q, f"eval_{idx}")
    lat = round(time.time() - start, 2)
    
    eval_data = evaluate_interaction(q, ans)
    
    return {
        "ID": idx + 1,
        "Tier": eval_data.get("tier"),
        "Intent": eval_data.get("intent_type"),
        "Score": eval_data.get("score", 0),
        "Question": q,
        "Answer": ans,
        "Reasoning": eval_data.get("reasoning"),
        "Suggestions": eval_data.get("suggestions"),
        "Source": eval_data.get("likely_source"),
        "Latency": lat
    }

# --- EXCEL FORMATTING FUNCTION ---
def create_fancy_excel(df, filename):
    print(f"--- Generating Smart Excel Report: {filename} ---")
    
    # Initialize the Excel Writer with XlsxWriter engine
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    
    # 1. Write the Data Sheet
    df.to_excel(writer, sheet_name='Evaluations', index=False)
    
    # Get Objects
    workbook = writer.book
    worksheet = writer.sheets['Evaluations']
    
    # --- DEFINING FORMATS ---
    header_fmt = workbook.add_format({
        'bold': True, 'text_wrap': True, 'valign': 'top', 'fg_color': '#4F81BD', 'font_color': 'white', 'border': 1
    })
    wrap_fmt = workbook.add_format({'text_wrap': True, 'valign': 'top'})
    center_fmt = workbook.add_format({'align': 'center', 'valign': 'top'})
    
    # Define Color Scales for Scores
    green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
    yellow_fmt = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500'})
    red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})

    # --- APPLYING FORMATS ---
    
    # Set Column Widths
    worksheet.set_column('A:A', 5, center_fmt)   # ID
    worksheet.set_column('B:C', 15, center_fmt)  # Tier, Intent
    worksheet.set_column('D:D', 8, center_fmt)   # Score
    worksheet.set_column('E:F', 50, wrap_fmt)    # Question, Answer
    worksheet.set_column('G:H', 40, wrap_fmt)    # Reasoning, Suggestions
    worksheet.set_column('I:J', 15, center_fmt)  # Source, Latency

    # Format Headers
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_fmt)
        
    # Conditional Formatting for Score Column (Column D is index 3)
    # Range: D2 to D[End]
    data_len = len(df) + 1
    rng = f"D2:D{data_len}"
    
    worksheet.conditional_format(rng, {'type': 'cell', 'criteria': '>=', 'value': 80, 'format': green_fmt})
    worksheet.conditional_format(rng, {'type': 'cell', 'criteria': 'between', 'minimum': 50, 'maximum': 79, 'format': yellow_fmt})
    worksheet.conditional_format(rng, {'type': 'cell', 'criteria': '<', 'value': 50, 'format': red_fmt})

    # --- 2. DASHBOARD SHEET (CHARTS) ---
    dash_sheet = workbook.add_worksheet('Dashboard')
    dash_sheet.hide_gridlines(2)
    
    # A. Calculate Stats
    avg_score = df['Score'].mean()
    pass_count = len(df[df['Score'] >= 70])
    fail_count = len(df[df['Score'] < 70])
    
    # Create Summary Table Data in Dashboard
    dash_sheet.write('B2', "Performance Summary", workbook.add_format({'bold': True, 'font_size': 14}))
    dash_sheet.write('B4', "Average Score")
    dash_sheet.write('C4', round(avg_score, 1), workbook.add_format({'bold': True, 'font_size': 12}))
    dash_sheet.write('B5', "Passed (>70)")
    dash_sheet.write('C5', pass_count)
    dash_sheet.write('B6', "Failed (<70)")
    dash_sheet.write('C6', fail_count)

    # B. Prepare Data for Charts (Write pivot data to hidden columns or side columns)
    # Intent Distribution
    intent_counts = df['Intent'].value_counts()
    dash_sheet.write('M1', 'Intent')
    dash_sheet.write('N1', 'Count')
    row = 1
    for intent, count in intent_counts.items():
        dash_sheet.write(row, 12, intent) # Col M
        dash_sheet.write(row, 13, count)  # Col N
        row += 1
        
    # C. Create Pie Chart (Intent)
    chart_pie = workbook.add_chart({'type': 'pie'})
    chart_pie.add_series({
        'name': 'Query Intents',
        'categories': ['Dashboard', 1, 12, row-1, 12],
        'values':     ['Dashboard', 1, 13, row-1, 13],
    })
    chart_pie.set_title({'name': 'Query Intent Distribution'})
    dash_sheet.insert_chart('E2', chart_pie)
    
    # D. Create Histogram/Bar for Scores (Bins)
    # Bin the scores: 0-20, 21-40, 41-60, 61-80, 81-100
    bins = [0, 20, 40, 60, 80, 100]
    labels = ['0-20', '21-40', '41-60', '61-80', '81-100']
    df['ScoreBin'] = pd.cut(df['Score'], bins=bins, labels=labels)
    score_dist = df['ScoreBin'].value_counts().sort_index()
    
    dash_sheet.write('M10', 'Score Range')
    dash_sheet.write('N10', 'Count')
    r_start = 11
    curr_r = r_start
    for label, count in score_dist.items():
        dash_sheet.write(curr_r, 12, label)
        dash_sheet.write(curr_r, 13, count)
        curr_r += 1

    chart_bar = workbook.add_chart({'type': 'column'})
    chart_bar.add_series({
        'name': 'Score Distribution',
        'categories': ['Dashboard', r_start, 12, curr_r-1, 12],
        'values':     ['Dashboard', r_start, 13, curr_r-1, 13],
        'fill':       {'color': '#4F81BD'}
    })
    chart_bar.set_title({'name': 'Response Quality Distribution'})
    chart_bar.set_x_axis({'name': 'Score Range'})
    chart_bar.set_y_axis({'name': 'Number of Queries'})
    dash_sheet.insert_chart('E18', chart_bar)

    writer.close()
    print("✅ Excel Report Generated Successfully.")

# --- MAIN ---
def main():
    if not os.path.exists(INPUT_CSV):
        print(f"❌ Error: {INPUT_CSV} not found.")
        return

    try:
        with open(INPUT_CSV, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip()]
        if lines and lines[0].lower().startswith('question'): lines = lines[1:]
        df_input = pd.DataFrame(lines, columns=['Question'])
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return

    questions = list(df_input.iterrows())
    results = []
    
    print(f"--- STARTING PRO EVALUATION (Workers: {MAX_WORKERS}) ---")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_row, q): q for q in questions}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                data = future.result()
                results.append(data)
                completed += 1
                print(f"[{completed}/{len(questions)}] Finished Q{data['ID']} - Score: {data['Score']}")
            except Exception as e:
                print(f"Worker Error: {e}")

    results.sort(key=lambda x: x["ID"])
    df_results = pd.DataFrame(results)
    
    # Generate the Smart Excel
    create_fancy_excel(df_results, OUTPUT_EXCEL)

if __name__ == "__main__":
    main()