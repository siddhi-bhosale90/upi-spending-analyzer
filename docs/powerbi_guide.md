# Building the Power BI dashboard

The Python pipeline writes Power BI-ready files to `outputs/`. This guide shows how to turn them
into an interactive dashboard in **Power BI Desktop** (free, Windows). The `.pbix` file itself is
not included in this repo: you build it from the CSVs below.

## 1. Load the data

*Home -> Get data -> Text/CSV*, then load:

| File | Use |
|---|---|
| `outputs/powerbi_transactions.csv` | One row per transaction: `date, month, month_start, description, amount, type, category, is_anomaly` |
| `outputs/monthly_category_summary.csv` | Month x category totals, transaction counts, `mom_pct_change`, `share_of_month_pct` |
| `outputs/category_contribution.csv` | Ranked categories with share and cumulative share |
| `outputs/anomalies_monthly.csv` | Months flagged as spikes, with the expected vs actual spend |

In Power Query check the data types: `date` and `month_start` = Date, `amount` = Decimal number,
`is_anomaly` = True/False.

## 2. Add a date table and measures

Modeling -> New table:

```DAX
DateTable = CALENDARAUTO()
```

Create a relationship `DateTable[Date]` -> `powerbi_transactions[date]` (many-to-one), then add
these measures to `powerbi_transactions`:

```DAX
Total Spend = CALCULATE(SUM(powerbi_transactions[amount]), powerbi_transactions[type] = "DEBIT")

Prev Month Spend = CALCULATE([Total Spend], DATEADD(DateTable[Date], -1, MONTH))

MoM % Change = DIVIDE([Total Spend] - [Prev Month Spend], [Prev Month Spend])

Category Share % =
DIVIDE([Total Spend], CALCULATE([Total Spend], ALL(powerbi_transactions[category])))

Flagged Payments = CALCULATE(COUNTROWS(powerbi_transactions), powerbi_transactions[is_anomaly] = TRUE())
```

## 3. Suggested report page

| Visual | Fields |
|---|---|
| KPI cards (3) | `Total Spend`, `MoM % Change`, `Flagged Payments` |
| Line chart: month-over-month trend | Axis `DateTable[Date]` (month), Values `Total Spend`, Legend `category` |
| Bar chart: largest contributors | Axis `category`, Values `Total Spend`, sort descending; tooltip `Category Share %` |
| Table: flagged payments | `date`, `description`, `category`, `amount`, filtered to `is_anomaly = True` |
| Slicers | `category`, `DateTable[Date]` |

Tip: use conditional formatting (red) on `MoM % Change` above +50% so spikes stand out.

## 4. Using your own data

Run `python run_analysis.py --input <your_statement.csv>` and press *Refresh* in Power BI: the
output file names stay the same.
