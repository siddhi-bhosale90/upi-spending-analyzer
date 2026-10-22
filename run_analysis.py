"""Run the full UPI spending analysis.

    python run_analysis.py                                  # analyse the bundled sample data
    python run_analysis.py --input my_statement.csv         # analyse your own export
"""
import argparse
import os

import pandas as pd

from upi_analyzer.anomalies import monthly_anomalies, transaction_anomalies
from upi_analyzer.cleaning import load_transactions
from upi_analyzer.reports import (category_contribution, monthly_pivot, monthly_summary,
                                  write_outputs)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Track UPI spending patterns and flag anomalies.")
    parser.add_argument("--input", default=os.path.join("data", "sample_upi_transactions.csv"))
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--txn-threshold", type=float, default=3.5,
                        help="robust z-score above which a payment is flagged (default 3.5)")
    parser.add_argument("--monthly-threshold", type=float, default=3.5,
                        help="robust z-score above which a month is flagged (default 3.5)")
    parser.add_argument("--min-increase", type=float, default=500.0,
                        help="ignore anomalies smaller than this many INR above normal (default 500)")
    args = parser.parse_args(argv)

    df, report = load_transactions(args.input)
    spend = df[df["type"] == "DEBIT"].copy()
    if spend.empty:
        raise SystemExit("No spending (DEBIT) transactions found in the input file.")

    pivot = monthly_pivot(spend)
    summary = monthly_summary(spend, pivot)
    contrib = category_contribution(spend)
    txn_anoms = transaction_anomalies(spend, threshold=args.txn_threshold,
                                      min_abs_increase=args.min_increase)
    month_anoms = monthly_anomalies(pivot, threshold=args.monthly_threshold,
                                    min_abs_increase=args.min_increase)
    write_outputs(df, spend, pivot, summary, contrib, txn_anoms, month_anoms, args.output_dir)

    totals = pivot.sum(axis=1)
    lines = [
        "UPI SPENDING ANALYSIS",
        f"Input: {args.input}",
        f"Rows read: {report['rows_in']} | kept: {report['rows_out']} | dropped (bad date/amount/type): "
        f"{report['dropped_bad_date']}/{report['dropped_bad_amount']}/{report['dropped_unknown_type']} | "
        f"possible duplicates kept: {report['possible_duplicates_kept']}",
        f"Period: {report['date_min']} to {report['date_max']} ({len(pivot)} months)",
        f"Total spend: INR {spend['amount'].sum():,.0f} across {len(spend)} payments; "
        f"monthly median INR {totals.median():,.0f}, mean INR {totals.mean():,.0f}",
        "",
        "Top contributors to spend:",
    ]
    for _, r in contrib.head(5).iterrows():
        lines.append(f"  {int(r['rank'])}. {r['category']:<18} INR {r['total_spend']:>9,.0f}  "
                     f"{r['share_pct']:>4.1f}%  (cumulative {r['cumulative_share_pct']:.1f}%)")
    lines += ["", f"Flagged payments ({len(txn_anoms)}):"]
    for _, r in txn_anoms.iterrows():
        lines.append(f"  {r['date']:%Y-%m-%d}  {r['description']:<26} {r['reason']}")
    lines += ["", f"Flagged months ({len(month_anoms)}):"]
    for _, r in month_anoms.iterrows():
        lines.append(f"  {r['reason']}")
    summary_text = "\n".join(lines)
    with open(os.path.join(args.output_dir, "summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(summary_text + "\n")
    print(summary_text)


if __name__ == "__main__":
    main()
