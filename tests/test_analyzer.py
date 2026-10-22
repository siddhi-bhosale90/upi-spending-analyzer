"""Unit tests. Run from the project root:  python -m unittest discover -v"""
import unittest

import pandas as pd

import generate_sample_data as sample
from upi_analyzer.anomalies import modified_z_scores, monthly_anomalies, transaction_anomalies
from upi_analyzer.categorize import categorize
from upi_analyzer.cleaning import clean_dataframe
from upi_analyzer.reports import category_contribution, monthly_pivot, monthly_summary


class CategorizeTests(unittest.TestCase):
    def test_known_merchants(self):
        cases = {
            "Swiggy": "Food & Dining",
            "BigBasket": "Groceries",
            "Uber": "Transport",
            "MSEDCL Electricity Bill": "Bills & Utilities",
            "Netflix": "Entertainment",
            "Amazon Prime Video": "Entertainment",
            "Amazon": "Shopping",
            "Apollo Pharmacy": "Health",
            "Coursera": "Education",
            "UPI Transfer - Rohan": "Transfers",
            "Some Random Shop": "Others",
        }
        for text, expected in cases.items():
            self.assertEqual(categorize(text), expected, text)

    def test_whole_word_matching(self):
        # "ola" must not match inside another word
        self.assertEqual(categorize("Coca-Cola Distributors"), "Others")
        self.assertEqual(categorize("Ola Cabs"), "Transport")


class CleaningTests(unittest.TestCase):
    def test_messy_statement_is_cleaned(self):
        raw = pd.DataFrame({
            "Transaction Date": ["05/01/2026", "06/01/2026", "not a date", "07/01/2026", "08/01/2026"],
            "Narration": ["Swiggy", "Uber", "Zomato", "Salary", "Netflix"],
            "Amount": ["Rs. 1,200.50", "85", "300", "20,000", "abc"],
            "Dr/Cr": ["DR", "Debit", "DR", "CR", "DR"],
        })
        df, report = clean_dataframe(raw)
        self.assertEqual(report["rows_in"], 5)
        self.assertEqual(report["dropped_bad_date"], 1)
        self.assertEqual(report["dropped_bad_amount"], 1)
        self.assertEqual(len(df), 3)
        first = df.iloc[0]
        self.assertEqual(first["date"], pd.Timestamp("2026-01-05"))  # day-first parsing
        self.assertAlmostEqual(first["amount"], 1200.50)
        self.assertEqual(first["type"], "DEBIT")
        self.assertEqual(df[df["description"] == "Salary"].iloc[0]["category"], "Credit")

    def test_missing_required_column_raises(self):
        with self.assertRaises(ValueError):
            clean_dataframe(pd.DataFrame({"date": ["2026-01-01"], "amount": ["10"]}))

    def test_separate_debit_credit_columns(self):
        raw = pd.DataFrame({
            "Date": ["2026-01-01", "2026-01-02"],
            "Details": ["Swiggy", "Refund"],
            "Debit": ["250", ""],
            "Credit": ["", "100"],
        })
        df, _ = clean_dataframe(raw)
        self.assertEqual(list(df["type"]), ["DEBIT", "CREDIT"])


class DetectorTests(unittest.TestCase):
    def test_modified_z_constant_series_is_all_zero(self):
        self.assertTrue((modified_z_scores(pd.Series([199.0] * 10)) == 0).all())

    def test_modified_z_flags_outlier(self):
        z = modified_z_scores(pd.Series([100, 110, 95, 105, 98, 102, 5000.0]))
        self.assertGreater(z.iloc[-1], 3.5)
        self.assertTrue((z.iloc[:-1].abs() < 3.5).all())

    def test_fixed_subscription_not_flagged(self):
        spend = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=12, freq="MS"),
            "description": "Netflix", "category": "Entertainment", "amount": 199.0,
        })
        self.assertTrue(transaction_anomalies(spend).empty)


class EndToEndTests(unittest.TestCase):
    """Run the detectors on the synthetic data, where the injected anomalies are known."""

    @classmethod
    def setUpClass(cls):
        df, _ = clean_dataframe(sample.generate())
        cls.df = df
        cls.spend = df[df["type"] == "DEBIT"].copy()
        cls.pivot = monthly_pivot(cls.spend)
        cls.txn = transaction_anomalies(cls.spend)
        cls.monthly = monthly_anomalies(cls.pivot)

    def test_all_injected_payments_are_found(self):
        found = {(d.date().isoformat(), desc, amt)
                 for d, desc, amt in zip(self.txn["date"], self.txn["description"], self.txn["amount"])}
        for date, description, amount, _why in sample.INJECTED_ANOMALIES:
            self.assertIn((date, description, float(amount)), found)

    def test_few_extra_flags(self):
        # 5 injected + a handful of naturally large grocery / transfer payments, not dozens.
        self.assertLessEqual(len(self.txn), len(sample.INJECTED_ANOMALIES) + 6)

    def test_injected_months_are_found(self):
        found = set(zip(self.monthly["month"], self.monthly["category"]))
        for pair in [("2025-10", "Shopping"), ("2026-05", "Bills & Utilities"),
                     ("2026-06", "Education"), ("2026-08", "Transfers")]:
            self.assertIn(pair, found)

    def test_summary_tables_are_consistent(self):
        summary = monthly_summary(self.spend, self.pivot)
        contrib = category_contribution(self.spend)
        self.assertAlmostEqual(summary["total_spend"].sum(), self.spend["amount"].sum(), places=0)
        self.assertAlmostEqual(contrib["share_pct"].sum(), 100.0, delta=0.5)
        self.assertEqual(contrib.iloc[0]["rank"], 1)
        self.assertEqual(len(self.pivot), 12)


if __name__ == "__main__":
    unittest.main()
