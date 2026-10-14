"""Load sales workbooks, calculate daily metrics, and write an LLM-assisted report."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

DATE_COLUMNS = ("orderdate", "saledate", "invoicedate", "transactiondate", "timestamp", "date")
REVENUE_COLUMNS = (
    "revenue",
    "totalsales",
    "salesamount",
    "saleamount",
    "netsales",
    "sales",
    "amount",
    "turnover",
)
QUANTITY_COLUMNS = ("quantity", "qty", "units", "unitsold")
PRODUCT_COLUMNS = ("product", "productname", "item", "itemname", "sku", "category")


def _normalise_column(column: Any) -> str:
    return "".join(character.lower() for character in str(column) if character.isalnum())


def _find_column(columns: list[Any], candidates: tuple[str, ...]) -> Any | None:
    normalised = {_normalise_column(column): column for column in columns}
    for candidate in candidates:
        if candidate in normalised:
            return normalised[candidate]
    for column in columns:
        name = _normalise_column(column)
        if any(candidate in name for candidate in candidates):
            return column
    return None


def load_workbooks(data_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    """Read every supported workbook and sheet; fail with the source name on bad input."""
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Sales data folder does not exist: {data_dir}")

    workbooks = sorted(
        file
        for file in data_dir.iterdir()
        if file.is_file()
        and file.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        and not file.name.startswith("~$")
    )
    if not workbooks:
        raise FileNotFoundError(
            f"No Excel workbooks found in {data_dir}. Add .xlsx, .xlsm, or .xls files."
        )

    frames: list[pd.DataFrame] = []
    for workbook in workbooks:
        try:
            sheets = pd.read_excel(workbook, sheet_name=None)
        except Exception as exc:
            raise ValueError(f"Could not read {workbook.name}: {exc}") from exc
        for sheet_name, frame in sheets.items():
            if not frame.empty:
                frame = frame.copy()
                frame["_source_file"] = f"{workbook.name} / {sheet_name}"
                frames.append(frame)

    if not frames:
        raise ValueError(f"Excel workbooks in {data_dir} contain no data rows.")
    return pd.concat(frames, ignore_index=True, sort=False), [file.name for file in workbooks]


def build_metrics(data: pd.DataFrame, report_date: date) -> tuple[dict[str, Any], pd.DataFrame]:
    """Filter to a report date when possible and calculate metrics from recognized columns."""
    date_column = _find_column(list(data.columns), DATE_COLUMNS)
    filtered = data.copy()
    date_filter_applied = False
    if date_column is not None:
        parsed_dates = pd.to_datetime(filtered[date_column], errors="coerce")
        filtered = filtered.loc[parsed_dates.dt.date == report_date].copy()
        date_filter_applied = True

    columns = [column for column in data.columns if not str(column).startswith("_")]
    revenue_column = _find_column(columns, REVENUE_COLUMNS)
    quantity_column = _find_column(columns, QUANTITY_COLUMNS)
    product_column = _find_column(columns, PRODUCT_COLUMNS)

    metrics: dict[str, Any] = {
        "report_date": report_date.isoformat(),
        "date_filter_applied": date_filter_applied,
        "rows_in_report": int(len(filtered)),
        "rows_in_all_workbooks": int(len(data)),
        "detected_columns": {
            "date": str(date_column) if date_column is not None else None,
            "revenue": str(revenue_column) if revenue_column is not None else None,
            "quantity": str(quantity_column) if quantity_column is not None else None,
            "product": str(product_column) if product_column is not None else None,
        },
    }
    if revenue_column is not None:
        values = pd.to_numeric(filtered[revenue_column], errors="coerce")
        metrics["total_sales"] = round(float(values.sum()), 2) if values.notna().any() else 0
        metrics["average_sale"] = round(float(values.mean()), 2) if values.notna().any() else 0
        if product_column is not None:
            by_product = filtered.assign(_sales_value=values).dropna(subset=["_sales_value"])
            top_products = (
                by_product.groupby(product_column, dropna=True)["_sales_value"]
                .sum()
                .sort_values(ascending=False)
                .head(5)
            )
            metrics["top_products_by_sales"] = [
                {"product": str(name), "sales": round(float(total), 2)}
                for name, total in top_products.items()
            ]
    if quantity_column is not None:
        values = pd.to_numeric(filtered[quantity_column], errors="coerce")
        metrics["units_sold"] = round(float(values.sum()), 2) if values.notna().any() else 0
    if product_column is not None:
        metrics["distinct_products"] = int(filtered[product_column].nunique(dropna=True))
    return metrics, filtered


def _create_model(model_name: str):
    if not model_name.strip():
        raise ValueError("Enter a Gemini model name before generating the report.")
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY is empty. Add a Gemini API key to the project .env file."
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0,
    )


def generate_report(
    metrics: dict[str, Any],
    source_files: list[str],
    model_name: str,
) -> str:
    model = _create_model(model_name)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a sales analyst. Write a concise daily sales report in Markdown. "
                "Use only the supplied calculated metrics; do not invent numbers or conclusions. "
                "Mention missing metrics or that there were no rows for the date when applicable. "
                "Include a short performance summary, key metrics, notable products, and one "
                "practical observation. Distinguish an unfiltered workbook summary from a daily "
                "report when no date column was detected.",
            ),
            (
                "human",
                "Source workbooks: {source_files}\n"
                "Calculated metrics (authoritative):\n{metrics}",
            ),
        ]
    )
    chain = prompt | model | StrOutputParser()
    try:
        return chain.invoke(
            {
                "source_files": ", ".join(source_files),
                "metrics": json.dumps(metrics, indent=2, ensure_ascii=False),
            }
        ).strip()
    except Exception as exc:
        if getattr(exc, "status_code", getattr(exc, "code", None)) in (401, 403):
            raise RuntimeError(
                "Google Gemini rejected GOOGLE_API_KEY (authentication error). Check that it is an "
                "active Gemini API key from https://aistudio.google.com/apikey, update "
                "the project .env file, and restart Streamlit. Do not paste the key into chat."
            ) from exc
        raise RuntimeError(f"Report generation with Gemini failed: {exc}") from exc


def run_report(
    report_date: date,
    model_name: str,
    data_dir: Path,
    reports_dir: Path,
) -> Path:
    data, source_files = load_workbooks(data_dir)
    metrics, _ = build_metrics(data, report_date)
    summary = generate_report(metrics, source_files, model_name)

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{report_date.isoformat()}_sales_report.md"
    content = (
        f"# Sales report — {report_date.isoformat()}\n\n"
        f"**LLM:** Google Gemini (`{model_name}`)  \n"
        f"**Source files:** {', '.join(source_files)}\n\n"
        f"## Calculated metrics\n\n```json\n{json.dumps(metrics, indent=2, ensure_ascii=False)}\n```\n\n"
        f"## Analysis\n\n{summary}\n"
    )
    report_path.write_text(content, encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a daily sales report from Excel files.")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="Report date (YYYY-MM-DD)")
    parser.add_argument("--model", help="Override the Gemini model configured in .env")
    args = parser.parse_args()

    default_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    reports_dir = Path(os.getenv("REPORTS_DIR", "reports"))
    if not data_dir.is_absolute():
        data_dir = PROJECT_DIR / data_dir
    if not reports_dir.is_absolute():
        reports_dir = PROJECT_DIR / reports_dir

    path = run_report(args.date, args.model or default_model, data_dir, reports_dir)
    print(f"Sales report saved to: {path}")


if __name__ == "__main__":
    main()
