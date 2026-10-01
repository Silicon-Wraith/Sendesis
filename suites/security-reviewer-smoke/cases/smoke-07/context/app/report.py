def _month(date: str) -> str:
    """'2026-09-30' -> '2026-09'."""
    return date[:7]


def monthly_totals(rows):
    totals = {}
    for row in rows:
        month = _month(row["date"])
        totals[month] = totals.get(month, 0) + row["amount"]
    return dict(sorted(totals.items()))
