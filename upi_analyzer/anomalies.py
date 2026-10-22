"""Anomaly detection for spending data.

Two complementary detectors, both based on *robust* statistics (median / MAD)
so that the unusual values we are hunting for do not distort their own baseline:

1. Transaction anomalies - a single payment that is unusually large for its
   category (modified z-score, Iglewicz & Hoaglin).
2. Monthly spike anomalies - a month whose total for a category (or overall)
   is far above what the other months suggest (leave-one-out baseline).

Only unusually *high* spending is flagged. Nothing is removed from the data;
anomalies are reported for a human to review (a flagged item is a prompt to
look, not proof of an error or fraud).
"""
import numpy as np
import pandas as pd

TXN_COLUMNS = ["date", "description", "category", "amount", "typical_amount", "score", "reason"]
MONTHLY_COLUMNS = ["month", "category", "total_spend", "expected_spend", "score",
                   "pct_above_expected", "mom_pct_change", "reason"]


def modified_z_scores(values: pd.Series) -> pd.Series:
    """Robust z-score: (x - median) / (1.4826 * MAD).

    Falls back to the mean absolute deviation when MAD is 0 (e.g. a fixed
    subscription that is nearly always the same amount) and returns zeros when
    every value is identical.
    """
    median = values.median()
    deviations = (values - median).abs()
    scale = 1.4826 * deviations.median()
    if scale == 0:
        scale = 1.2533 * deviations.mean()
    if scale == 0:
        return pd.Series(0.0, index=values.index)
    return (values - median) / scale


def transaction_anomalies(spend: pd.DataFrame, threshold: float = 3.5,
                          min_transactions: int = 8, min_abs_increase: float = 500.0) -> pd.DataFrame:
    """Flag individual payments that are unusually large for their category.

    A payment is flagged when its robust z-score is above ``threshold`` AND it is
    at least ``min_abs_increase`` INR above the category's typical (median) payment.
    The second condition is a practical-significance filter: statistically
    "unusual" but tiny differences (a INR 374 auto ride) are not worth a review.

    Categories with fewer than ``min_transactions`` payments are skipped because
    there is not enough history to define "usual".
    """
    rows = []
    for category, group in spend.groupby("category"):
        if len(group) < min_transactions:
            continue
        z = modified_z_scores(group["amount"])
        typical = float(group["amount"].median())
        flagged = (z > threshold) & (group["amount"] - typical >= min_abs_increase)
        for idx in group.index[flagged]:
            amount = float(group.at[idx, "amount"])
            rows.append({
                "date": group.at[idx, "date"],
                "description": group.at[idx, "description"],
                "category": category,
                "amount": amount,
                "typical_amount": typical,
                "score": round(float(z.at[idx]), 1),
                "reason": (f"INR {amount:,.0f} is {amount / typical:.1f}x the typical "
                           f"{category} payment (median INR {typical:,.0f})"),
            })
    out = pd.DataFrame(rows, columns=TXN_COLUMNS)
    return out.sort_values("score", ascending=False).reset_index(drop=True)


def monthly_anomalies(pivot: pd.DataFrame, threshold: float = 3.5, min_ratio: float = 1.25,
                      min_abs_increase: float = 500.0, min_active_months: int = 4,
                      min_spread: float = 250.0) -> pd.DataFrame:
    """Flag months whose spend is far above the other months.

    ``pivot`` has one row per month (index) and one column per category.
    A TOTAL column is added automatically. For each month the baseline is the
    median of the *other* months and the spread is their MAD (never less than
    15% of the baseline or ``min_spread`` INR, so sparse categories whose usual
    spend is ~0 do not produce absurd scores). A month is flagged only if all
    three hold, which keeps small, noisy categories from raising alarms:

      * robust z-score above ``threshold``
      * spend at least ``min_ratio`` times the baseline
      * at least ``min_abs_increase`` INR above the baseline
    """
    data = pivot.copy()
    data["TOTAL"] = data.sum(axis=1)
    rows = []
    for category in data.columns:
        series = data[category].astype(float)
        for month in series.index:
            others = series.drop(month)
            if (others > 0).sum() < min_active_months:
                continue
            baseline = float(others.median())
            spread = 1.4826 * float((others - baseline).abs().median())
            spread = max(spread, 0.15 * baseline, min_spread)
            value = float(series[month])
            score = (value - baseline) / spread
            if score > threshold and value >= min_ratio * baseline and value - baseline >= min_abs_increase:
                pos = list(series.index).index(month)
                prev = float(series.iloc[pos - 1]) if pos > 0 else np.nan
                mom = (value - prev) / prev * 100 if prev and prev > 0 else np.nan
                rows.append({
                    "month": month,
                    "category": category,
                    "total_spend": round(value, 2),
                    "expected_spend": round(baseline, 2),
                    "score": round(score, 1),
                    "pct_above_expected": round((value / baseline - 1) * 100, 1) if baseline > 0 else np.nan,
                    "mom_pct_change": round(mom, 1) if mom == mom else np.nan,
                    "reason": (f"{category} spend of INR {value:,.0f} in {month} vs "
                               f"typical INR {baseline:,.0f} for other months"),
                })
    out = pd.DataFrame(rows, columns=MONTHLY_COLUMNS)
    return out.sort_values(["score"], ascending=False).reset_index(drop=True)
