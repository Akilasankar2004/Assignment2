"""Streamlit dashboard for generating sales reports from local Excel workbooks."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from sales_report import build_metrics, generate_report, load_workbooks

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

st.set_page_config(page_title="Daily Sales Report", page_icon="📊", layout="wide")
st.title("Daily Sales Report")
st.caption("Analyze Excel sales workbooks with Google Gemini using your API key.")

data_dir = Path(os.getenv("DATA_DIR", "data"))
if not data_dir.is_absolute():
    data_dir = PROJECT_DIR / data_dir
reports_dir = Path(os.getenv("REPORTS_DIR", "reports"))
if not reports_dir.is_absolute():
    reports_dir = PROJECT_DIR / reports_dir

with st.sidebar:
    st.header("Report settings")
    env_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    model_name = st.text_input("Model", value=env_model)
    report_date = st.date_input("Report date", value=date.today())
    st.caption(f"Excel folder: `{data_dir}`")
    st.caption(
        "Gemini API key: "
        + ("configured" if os.getenv("GOOGLE_API_KEY", "").strip() else "missing in .env")
    )

try:
    sales_data, source_files = load_workbooks(data_dir)
except (FileNotFoundError, ValueError) as exc:
    st.warning(str(exc))
    st.info("Place your Excel sales files in the project's `data` folder.")
    st.stop()

st.write("**Loaded workbooks:** " + ", ".join(source_files))
metrics, daily_data = build_metrics(sales_data, report_date)
if not metrics["date_filter_applied"]:
    st.warning("No date column was detected; metrics use all rows in the workbooks.")

left, middle, right = st.columns(3)
left.metric("Rows for report", metrics["rows_in_report"])
if "total_sales" in metrics:
    middle.metric("Total sales", f'{metrics["total_sales"]:,.2f}')
else:
    middle.metric("Total sales", "No sales amount column detected")
if "units_sold" in metrics:
    right.metric("Units sold", f'{metrics["units_sold"]:,.2f}')
else:
    right.metric("Units sold", "No quantity column detected")

product_sales = metrics.get("top_products_by_sales", [])
if product_sales:
    st.subheader("Top products for selected date")
    chart_data = pd.DataFrame(product_sales).set_index("product")
    st.bar_chart(chart_data)

with st.expander("Preview included sales rows"):
    st.dataframe(daily_data.drop(columns=["_source_file"], errors="ignore"), use_container_width=True)

if st.button("Generate and save report", type="primary"):
    with st.spinner("Generating report with Google Gemini..."):
        try:
            analysis = generate_report(metrics, source_files, model_name.strip())
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_path = reports_dir / f"{report_date.isoformat()}_sales_report.md"
            report_path.write_text(
                f"# Sales report — {report_date.isoformat()}\n\n"
                f"**LLM:** Google Gemini (`{model_name.strip()}`)  \n"
                f"**Source files:** {', '.join(source_files)}\n\n"
                f"## Calculated metrics\n\n```json\n"
                f"{json.dumps(metrics, indent=2, ensure_ascii=False)}\n```\n\n"
                f"## Analysis\n\n{analysis}\n",
                encoding="utf-8",
            )
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Report saved to `{report_path}`")
            st.markdown(analysis)
