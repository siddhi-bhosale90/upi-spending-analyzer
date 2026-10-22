"""Rule-based categorisation of UPI transactions from the payee / description text.

Rules are checked in the order below and the first match wins. Anything that
matches no rule falls into "Others". Add your own keywords to improve accuracy
for the merchants you actually use.
"""
import re

CATEGORY_KEYWORDS = {
    "Transfers": ["upi transfer", "sent to", "transfer to"],
    "Food & Dining": [
        "swiggy", "zomato", "dominos", "domino's", "mcdonalds", "mcdonald's", "kfc",
        "cafe", "restaurant", "chai", "pizza", "burger", "starbucks", "bakery",
        "canteen", "mess", "hotel",
    ],
    "Groceries": [
        "bigbasket", "blinkit", "zepto", "dmart", "d-mart", "instamart",
        "reliance fresh", "grocery", "kirana", "vegetable", "supermarket",
    ],
    "Transport": [
        "uber", "ola", "rapido", "irctc", "redbus", "metro", "petrol", "fuel",
        "bpcl", "hpcl", "indian oil", "fastag", "parking", "pmpml", "bus pass",
    ],
    "Bills & Utilities": [
        "electricity", "msedcl", "mahadiscom", "jio", "airtel", "vodafone idea",
        "bsnl", "recharge", "broadband", "wifi", "gas", "water bill", "dth",
        "bill payment",
    ],
    "Entertainment": [
        "netflix", "spotify", "hotstar", "prime video", "youtube premium",
        "bookmyshow", "pvr", "inox", "gaming", "steam",
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa", "decathlon",
        "croma", "reliance digital", "lifestyle",
    ],
    "Health": [
        "pharmacy", "apollo", "medplus", "1mg", "pharmeasy", "hospital", "clinic",
        "diagnostic", "dental",
    ],
    "Education": [
        "udemy", "coursera", "unacademy", "nptel", "college", "tuition",
        "stationery", "books", "exam fee", "course",
    ],
}

# Whole-word matching avoids false hits such as "ola" inside "Coca-Cola".
_PATTERNS = {
    category: re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keywords) + r")\b", re.IGNORECASE)
    for category, keywords in CATEGORY_KEYWORDS.items()
}


def categorize(text: str) -> str:
    """Return the spending category for a payee / description string."""
    text = "" if text is None else str(text)
    for category, pattern in _PATTERNS.items():
        if pattern.search(text):
            return category
    return "Others"
