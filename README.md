# Daily Sales Report

A local Streamlit application that reads Excel workbooks from `data`, calculates daily sales metrics, and asks Google Gemini through LangChain to write a Markdown analysis. It uses a Google Gemini API key only; it does not use Ollama or OpenRouter. The calculated metrics are shown separately from the LLM analysis so the arithmetic remains auditable.

## Setup

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

3. A sample workbook, `data/sample_sales.xlsx`, is included to try the app. Replace or supplement it with your `.xlsx`, `.xlsm`, or `.xls` sales workbooks. Every non-empty sheet in those workbooks is included.
4. Create a Gemini API key at [Google AI Studio](https://aistudio.google.com/apikey) and set `GOOGLE_API_KEY` in the project `.env` file. Keep the key private and do not commit it. Gemini API keys generally start with `AIza`.
5. Start the dashboard:

   ```powershell
   streamlit run app.py
   ```

## Daily reports

The dashboard's **Generate and save report** button creates `reports/YYYY-MM-DD_sales_report.md`.

To generate a report once from PowerShell:

```powershell
python -m sales_report
```

You can choose another report date with `python -m sales_report --date 2026-10-14`, or override the Gemini model with `--model gemini-3.8-flash`.

To automate daily generation on Windows, run the following once from PowerShell in this folder. It registers a current-user Windows Task Scheduler task for 08:00 local time by default:

```powershell
.\register_daily_task.ps1
```

Choose another 24-hour local time with `.\register_daily_task.ps1 -Time "18:30"`. The task uses `.venv\Scripts\python.exe` when available, otherwise `python` from your PATH, and runs in this project folder. Ensure the Gemini API key is configured and the machine has internet access at the scheduled time. To remove the task later:

```powershell
Unregister-ScheduledTask -TaskName "Daily Sales Report" -Confirm:$false
```

## Data handling

The app detects common date, sales/revenue, quantity, and product column names. When it finds a date column, it filters rows to the selected report date; without one, it reports on all workbook rows and labels that limitation. Review the detected metrics and workbook headers if your column names are unusual. Workbooks are read locally and are not sent to the model; only the aggregated metrics and source file names are included in the LLM prompt.

Run the focused metric tests with `python -m unittest discover -s tests`.

## Gemini authentication troubleshooting

If the app reports an invalid key or returns HTTP 401, verify that `GOOGLE_API_KEY` contains an active Gemini API key created in [Google AI Studio](https://aistudio.google.com/apikey). Replace the value in `.env` and restart Streamlit. Revoke and replace any key that has been shared in a chat or otherwise exposed.
