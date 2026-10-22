"""Load a transaction CSV, validate it and return a clean, analysis-ready table.

Expected columns (names are matched case-insensitively, common aliases accepted):

    date          transaction date (YYYY-MM-DD or DD/MM/YYYY)
    description   payee / merchant / narration text
    amount        transaction amount in INR (symbols and commas are stripped)
    type          DEBIT or CREDIT (optional, see below)

If there is no ``type`` column, positive amounts are treated as spends (DEBIT)
and negative amounts as credits. Statements with separate ``debit`` and
``credit`` columns are also supported.
"""
import re

import numpy as np
import pandas as pd

from .categorize import categorize

COLUMN_ALIASES = {
    "date": ["date", "transaction date", "txn date", "value date", "timestamp"],
    "description": ["description", "details", "narration", "merchant", "payee",
                    "particulars", "remarks", "transaction details"],
    "amount": ["amount", "amount (inr)", "amount(inr)", "transaction amount"],
    "type": ["type", "transaction type", "dr/cr", "debit/credit", "cr/dr"],
    "txn_id": ["transaction id", "txn id", "utr", "reference no", "reference number"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: re.sub(r"\s+", " ", str(c).strip().lower()) for c in df.columns})
    renames, used = {}, set()
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns and target not in used:
                renames[alias] = target
                used.add(target)
                break
    return df.rename(columns=renames)


def _parse_dates(series: pd.Series) -> pd.Series:
    """Parse ISO dates first, then fall back to day-first formats (Indian statements)."""
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed[missing] = pd.to_datetime(text[missing], dayfirst=True, errors="coerce", format="mixed")
    return parsed


def _parse_amount(series: pd.Series) -> pd.Series:
    """Strip currency symbols / commas ("Rs. 1,200.50" -> 1200.5)."""
    text = (series.astype(str)
            .str.replace(r"(?i)\b(?:rs|inr)\b\.?|\u20b9", "", regex=True)  # "Rs.", "INR", rupee sign
            .str.replace(r"[^\d.\-]", "", regex=True))                     # commas, spaces, etc.
    return pd.to_numeric(text, errors="coerce")


def _parse_type(raw: pd.Series) -> pd.Series:
    t = raw.astype(str).str.strip().str.lower()
    credit = t.str.contains(r"^(?:cr|c$|credit|received|income|deposit)", regex=True)
    debit = t.str.contains(r"^(?:dr|d$|debit|paid|sent|withdraw|expense)", regex=True)
    return pd.Series(np.select([credit, debit], ["CREDIT", "DEBIT"], default="UNKNOWN"), index=raw.index)


def clean_dataframe(raw: pd.DataFrame):
    """Validate and clean a raw transactions table. Returns (clean_df, report)."""
    df = _normalize_columns(raw.copy())
    report = {"rows_in": len(df)}

    # Statements that use separate debit / credit columns.
    if "amount" not in df.columns and {"debit", "credit"} <= set(df.columns):
        debit = _parse_amount(df["debit"]).fillna(0)
        credit = _parse_amount(df["credit"]).fillna(0)
        df["amount"] = debit.where(debit > 0, credit)
        df["type"] = np.where(debit > 0, "DEBIT", "CREDIT")

    missing_cols = [c for c in ("date", "description", "amount") if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required column(s): {missing_cols}. Found columns: {list(df.columns)}"
        )

    df["date"] = _parse_dates(df["date"])
    df["amount"] = _parse_amount(df["amount"])
    df["description"] = df["description"].fillna("").astype(str).str.strip()

    if "type" in df.columns:
        df["type"] = _parse_type(df["type"])
    else:
        df["type"] = np.where(df["amount"] < 0, "CREDIT", "DEBIT")
    df["amount"] = df["amount"].abs()

    # Validation: drop rows that cannot be analysed, and say how many.
    bad_date = df["date"].isna()
    bad_amount = df["amount"].isna() | (df["amount"] <= 0)
    bad_type = df["type"] == "UNKNOWN"
    report["dropped_bad_date"] = int(bad_date.sum())
    report["dropped_bad_amount"] = int((bad_amount & ~bad_date).sum())
    report["dropped_unknown_type"] = int((bad_type & ~bad_date & ~bad_amount).sum())
    df = df[~(bad_date | bad_amount | bad_type)].copy()

    # Duplicates: only removable when a transaction id exists; otherwise just reported,
    # because two identical payments on one day can be genuine.
    report["duplicates_dropped"] = 0
    if "txn_id" in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset="txn_id", keep="first")
        report["duplicates_dropped"] = before - len(df)
    report["possible_duplicates_kept"] = int(
        df.duplicated(subset=["date", "description", "amount", "type"]).sum()
    )

    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["month_start"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["category"] = np.where(df["type"] == "DEBIT", df["description"].map(categorize), "Credit")

    keep = ["date", "month", "month_start", "description", "amount", "type", "category"]
    df = df[keep].sort_values("date").reset_index(drop=True)

    report["rows_out"] = len(df)
    if len(df):
        report["date_min"] = df["date"].min().date().isoformat()
        report["date_max"] = df["date"].max().date().isoformat()
    return df, report


def load_transactions(path: str):
    """Read a CSV file and return (clean_df, report)."""
    return clean_dataframe(pd.read_csv(path, dtype=str))
