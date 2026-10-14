import unittest
from datetime import date
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path

import pandas as pd

from sales_report import _create_model, build_metrics, load_workbooks


class BuildMetricsTests(unittest.TestCase):
    def test_filters_report_date_and_calculates_sales_metrics(self):
        data = pd.DataFrame(
            {
                "Order Date": ["2026-10-14", "2026-10-13", "2026-10-14"],
                "Product Name": ["Widget", "Gadget", "Widget"],
                "Sales Amount": [125.50, 80.00, 74.50],
                "Quantity": [2, 1, 1],
            }
        )

        metrics, daily_rows = build_metrics(data, date(2026, 10, 14))

        self.assertEqual(len(daily_rows), 2)
        self.assertEqual(metrics["rows_in_all_workbooks"], 3)
        self.assertEqual(metrics["total_sales"], 200.0)
        self.assertEqual(metrics["average_sale"], 100.0)
        self.assertEqual(metrics["units_sold"], 3)
        self.assertEqual(metrics["distinct_products"], 1)
        self.assertEqual(metrics["top_products_by_sales"], [{"product": "Widget", "sales": 200.0}])
        self.assertTrue(metrics["date_filter_applied"])

    def test_uses_all_rows_when_date_column_is_missing(self):
        data = pd.DataFrame({"Product": ["Widget", "Gadget"], "Revenue": [10, 20]})

        metrics, rows = build_metrics(data, date(2026, 10, 14))

        self.assertEqual(len(rows), 2)
        self.assertEqual(metrics["total_sales"], 30.0)
        self.assertFalse(metrics["date_filter_applied"])
        self.assertIsNone(metrics["detected_columns"]["date"])

    def test_loads_nonempty_sheets_from_excel_workbooks(self):
        with TemporaryDirectory() as temporary_directory:
            workbook_path = Path(temporary_directory) / "sales.xlsx"
            with pd.ExcelWriter(workbook_path) as writer:
                pd.DataFrame({"Date": ["2026-10-14"], "Sales": [35]}).to_excel(
                    writer, sheet_name="Daily", index=False
                )
                pd.DataFrame({"Date": ["2026-10-13"], "Sales": [20]}).to_excel(
                    writer, sheet_name="Previous", index=False
                )

            rows, source_files = load_workbooks(Path(temporary_directory))

        self.assertEqual(len(rows), 2)
        self.assertEqual(source_files, ["sales.xlsx"])
        self.assertEqual(set(rows["_source_file"]), {"sales.xlsx / Daily", "sales.xlsx / Previous"})


class GeminiConfigurationTests(unittest.TestCase):
    def test_requires_google_api_key(self):
        with patch.dict("os.environ", {"GOOGLE_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "GOOGLE_API_KEY is empty"):
                _create_model("gemini-3.8-flash")

    def test_builds_gemini_chat_model_from_google_api_key(self):
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "AQ.test-gemini-key"}):
            model = _create_model("gemini-3.8-flash")

        self.assertEqual(model.model, "gemini-3.8-flash")


if __name__ == "__main__":
    unittest.main()
