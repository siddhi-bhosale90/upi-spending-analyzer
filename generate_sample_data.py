"""Generate a SYNTHETIC UPI transaction history for demos and tests.

This is NOT real data. It simulates a student's UPI activity for 12 months
(Oct 2025 - Sep 2026) from a fixed random seed, and deliberately injects a few
unusual payments (see INJECTED_ANOMALIES) so the detectors can be checked
against a known answer.

Usage:
    python generate_sample_data.py            # writes data/sample_upi_transactions.csv
"""
import calendar
import os

import numpy as np
import pandas as pd

SEED = 42
MONTHS = pd.period_range("2025-10", "2026-09", freq="M")

# (merchants, average payments per month, median amount in INR, log-normal sigma)
SPENDING_PROFILES = [
    (["Swiggy", "Zomato", "Dominos Pizza", "Campus Canteen", "Cafe Coffee Day", "Chai Point"], 14, 230, 0.35),
    (["BigBasket", "Blinkit", "DMart", "Local Kirana Store", "Zepto"], 5, 520, 0.35),
    (["Uber", "Ola", "Rapido", "PMPML Bus Pass", "IRCTC"], 11, 110, 0.50),
    (["Apollo Pharmacy", "MedPlus"], 1.2, 280, 0.40),
    (["BookMyShow", "PVR Cinemas"], 1.0, 420, 0.30),
    (["Amazon", "Flipkart", "Myntra", "Decathlon"], 1.8, 900, 0.55),
    (["Stationery Shop", "Udemy", "Unacademy"], 1.0, 350, 0.50),
    (["UPI Transfer - Rohan", "UPI Transfer - Priya", "UPI Transfer - Aditya"], 3.5, 300, 0.60),
]

# Fixed monthly payments: (merchant, amount, day of month)
RECURRING = [("Jio Recharge", 299, 5), ("Netflix", 199, 12), ("Spotify", 119, 15)]

# Deliberately unusual payments: (date, description, amount, why)
INJECTED_ANOMALIES = [
    ("2025-10-19", "Myntra", 9800, "festive sale shopping"),
    ("2026-03-14", "Zomato", 2850, "group dinner"),
    ("2026-05-09", "MSEDCL Electricity Bill", 3450, "summer electricity spike"),
    ("2026-06-22", "Coursera", 8999, "annual course subscription"),
    ("2026-08-27", "UPI Transfer - Rohan", 6000, "shared trip expense"),
]


def generate() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    for period in MONTHS:
        days = calendar.monthrange(period.year, period.month)[1]

        def day(d):
            return pd.Timestamp(period.year, period.month, min(d, days)).date().isoformat()

        rows.append((day(1), "UPI Credit - Monthly Allowance", 14000, "CREDIT"))

        for merchants, per_month, median, sigma in SPENDING_PROFILES:
            for _ in range(rng.poisson(per_month)):
                amount = max(20, int(round(median * np.exp(sigma * rng.standard_normal()))))
                rows.append((day(int(rng.integers(1, days + 1))), str(rng.choice(merchants)), amount, "DEBIT"))

        for merchant, amount, d in RECURRING:
            rows.append((day(d), merchant, amount, "DEBIT"))

        # Electricity: roughly constant, a bit higher in the hot months (Apr-Jun).
        seasonal = 1.2 if period.month in (4, 5, 6) else 1.0
        bill = int(round(850 * seasonal * (1 + 0.08 * rng.standard_normal())))
        rows.append((day(9), "MSEDCL Electricity Bill", bill, "DEBIT"))

    for date, description, amount, _why in INJECTED_ANOMALIES:
        # Replace the normal electricity bill in the spike month, add the rest on top.
        if description == "MSEDCL Electricity Bill":
            rows = [r for r in rows if not (r[0][:7] == date[:7] and r[1] == description)]
        rows.append((date, description, amount, "DEBIT"))

    df = pd.DataFrame(rows, columns=["date", "description", "amount", "type"])
    return df.sort_values(["date", "description"]).reset_index(drop=True)


if __name__ == "__main__":
    out_path = os.path.join("data", "sample_upi_transactions.csv")
    os.makedirs("data", exist_ok=True)
    frame = generate()
    frame.to_csv(out_path, index=False)
    print(f"Wrote {len(frame)} synthetic transactions to {out_path}")
