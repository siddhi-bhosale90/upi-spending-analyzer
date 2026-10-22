"""Monthly trends, category contribution, CSV exports and charts."""
import math
import os

import matplotlib

matplotlib.use("Agg")  # render to files; no display needed
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, ORANGE, RED, GREY = "#4C72B0", "#DD8452", "#C44E52", "#B8B8B8"

plt.rcParams.update({
    "figure.dpi": 130, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
})


def _inr(x, _pos=None):
    """Axis label: 1500 -> '1.5k', 2000 -> '2k', 800 -> '800'."""
    if abs(x) >= 1000:
        return f"{x / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return f"{x:.0f}"


# ----------------------------------------------------------------------------- tables

def monthly_pivot(spend: pd.DataFrame) -> pd.DataFrame:
    """Month x category totals, with months that had no spend filled in as 0."""
    months = pd.period_range(spend["date"].min(), spend["date"].max(), freq="M").astype(str)
    pivot = spend.pivot_table(index="month", columns="category", values="amount",
                              aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(months, fill_value=0)
    pivot.index.name = "month"
    pivot.columns.name = None
    return pivot


def monthly_summary(spend: pd.DataFrame, pivot: pd.DataFrame) -> pd.DataFrame:
    """Long table (month, category) with totals, counts, MoM change and share of the month."""
    long = pivot.reset_index().melt(id_vars="month", var_name="category", value_name="total_spend")
    counts = spend.groupby(["month", "category"]).size().rename("txn_count").reset_index()
    long = long.merge(counts, how="left", on=["month", "category"])
    long["txn_count"] = long["txn_count"].fillna(0).astype(int)
    long = long.sort_values(["category", "month"]).reset_index(drop=True)
    long["mom_pct_change"] = (
        long.groupby("category")["total_spend"].pct_change().replace([np.inf, -np.inf], np.nan) * 100
    ).round(1)
    month_total = long.groupby("month")["total_spend"].transform("sum")
    long["share_of_month_pct"] = (long["total_spend"] / month_total * 100).round(1)
    long["total_spend"] = long["total_spend"].round(2)
    return long.sort_values(["month", "total_spend"], ascending=[True, False]).reset_index(drop=True)


def category_contribution(spend: pd.DataFrame) -> pd.DataFrame:
    """Which categories drive total spend (ranked, with cumulative share)."""
    out = spend.groupby("category")["amount"].agg(
        total_spend="sum", txn_count="count", avg_txn="mean", median_txn="median"
    ).sort_values("total_spend", ascending=False)
    out["share_pct"] = out["total_spend"] / out["total_spend"].sum() * 100
    out["cumulative_share_pct"] = out["share_pct"].cumsum()
    out.insert(0, "rank", range(1, len(out) + 1))
    return out.round(1).reset_index()


# ----------------------------------------------------------------------------- charts

def plot_category_trends(pivot, monthly_anoms, path):
    """Small multiples: month-over-month spend for every category, anomalies in red."""
    cats = list(pivot.sum().sort_values(ascending=False).index)
    ncols = 3
    nrows = math.ceil(len(cats) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(13, 3.1 * nrows), sharex=True)
    axes = np.atleast_1d(axes).ravel()
    x = np.arange(len(pivot))
    flagged = monthly_anoms[monthly_anoms["category"] != "TOTAL"]
    for ax, cat in zip(axes, cats):
        ax.plot(x, pivot[cat].values, color=BLUE, linewidth=2, marker="o", markersize=3)
        pts = flagged[flagged["category"] == cat]
        for month in pts["month"]:
            i = list(pivot.index).index(month)
            ax.plot(i, pivot[cat].iloc[i], marker="D", color=RED, markersize=8, linestyle="none")
        ax.set_title(f"{cat}  (avg INR {pivot[cat].mean():,.0f}/mo)", fontsize=10.5)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_inr))
        ax.set_ylim(bottom=0)
        ax.set_xticks(x[::2])
        ax.set_xticklabels([pivot.index[i] for i in x[::2]], rotation=45, ha="right", fontsize=8)
    for ax in axes[len(cats):]:
        ax.set_visible(False)
    fig.suptitle("Month-over-month spend by category (red diamonds = flagged months; y-axes differ)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_top_contributors(contrib, path):
    """Ranked bars: the largest contributors to total spend."""
    data = contrib.sort_values("total_spend")
    colors = [BLUE if r <= 3 else GREY for r in data["rank"]]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(data["category"], data["total_spend"], color=colors)
    for bar, share in zip(bars, data["share_pct"]):
        ax.text(bar.get_width() + data["total_spend"].max() * 0.01, bar.get_y() + bar.get_height() / 2,
                f"INR {bar.get_width():,.0f}  ({share:.0f}%)", va="center", fontsize=9)
    top3 = contrib.head(3)
    ax.set_title(f"Top 3 categories make up {top3['share_pct'].sum():.0f}% of total spend")
    ax.set_xlabel("Total spend over the period (INR)")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_inr))
    ax.set_xlim(0, data["total_spend"].max() * 1.28)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_monthly_total(pivot, monthly_anoms, path):
    """Total monthly spend with typical level and months where a category spiked."""
    total = pivot.sum(axis=1)
    x = np.arange(len(total))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    spike_months = set(monthly_anoms["month"])
    for i, month in enumerate(total.index):
        if month in spike_months:
            ax.axvspan(i - 0.4, i + 0.4, color=ORANGE, alpha=0.25, linewidth=0)
    ax.plot(x, total.values, color=BLUE, linewidth=2.2, marker="o")
    ax.axhline(total.median(), color="#555555", linestyle="--", linewidth=1,
               label=f"Median month: INR {total.median():,.0f}")
    tot_flag = monthly_anoms[monthly_anoms["category"] == "TOTAL"]
    for month in tot_flag["month"]:
        i = list(total.index).index(month)
        ax.plot(i, total.iloc[i], marker="D", color=RED, markersize=9, linestyle="none")
    ax.plot([], [], marker="D", color=RED, linestyle="none", label="Total spend flagged")
    ax.fill_between([], [], [], color=ORANGE, alpha=0.25, label="Month with a flagged category")
    ax.set_xticks(x)
    ax.set_xticklabels(total.index, rotation=45, ha="right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_inr))
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Total spend (INR)")
    ax.set_title(f"Monthly spend: {len(spike_months)} of {len(total)} months contain a flagged spike")
    ax.legend(loc="lower center", ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_transaction_anomalies(spend, txn_anoms, path):
    """Every payment over time (log scale); flagged payments highlighted and labelled."""
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.scatter(spend["date"], spend["amount"], s=14, color=GREY, alpha=0.8, label="Normal payments")
    if len(txn_anoms):
        ax.scatter(txn_anoms["date"], txn_anoms["amount"], s=70, color=RED, marker="D",
                   label="Flagged payments", zorder=3)
        for k, (_, r) in enumerate(txn_anoms.head(6).iterrows()):
            ax.annotate(f"{r['description']}\nINR {r['amount']:,.0f}", (r["date"], r["amount"]),
                        xytext=(8, 10 if k % 2 == 0 else -26), textcoords="offset points", fontsize=8,
                        arrowprops=dict(arrowstyle="-", color="#888888", lw=0.6))
    ax.set_yscale("log")
    ax.set_ylim(top=spend["amount"].max() * 3)  # headroom so labels do not hit the title
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    ax.set_ylabel("Payment amount (INR, log scale)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_title(f"{len(txn_anoms)} payments flagged as unusually large for their category")
    ax.legend(loc="lower right", frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- export

def write_outputs(df, spend, pivot, summary, contrib, txn_anoms, monthly_anoms, out_dir):
    """Write CSVs (Power BI-ready) and PNG charts into ``out_dir``."""
    chart_dir = os.path.join(out_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)

    # Flag anomalous payments in the full transaction table (for Power BI conditional formatting).
    keys = set(zip(txn_anoms["date"], txn_anoms["description"], txn_anoms["amount"]))
    pbi = df.copy()
    pbi["is_anomaly"] = [k in keys for k in zip(pbi["date"], pbi["description"], pbi["amount"])]
    pbi.to_csv(os.path.join(out_dir, "powerbi_transactions.csv"), index=False)
    summary.to_csv(os.path.join(out_dir, "monthly_category_summary.csv"), index=False)
    contrib.to_csv(os.path.join(out_dir, "category_contribution.csv"), index=False)
    txn_anoms.to_csv(os.path.join(out_dir, "anomalies_transactions.csv"), index=False)
    monthly_anoms.to_csv(os.path.join(out_dir, "anomalies_monthly.csv"), index=False)

    plot_category_trends(pivot, monthly_anoms, os.path.join(chart_dir, "1_monthly_trends_by_category.png"))
    plot_top_contributors(contrib, os.path.join(chart_dir, "2_top_contributors.png"))
    plot_monthly_total(pivot, monthly_anoms, os.path.join(chart_dir, "3_monthly_total_spend.png"))
    plot_transaction_anomalies(spend, txn_anoms, os.path.join(chart_dir, "4_flagged_transactions.png"))
