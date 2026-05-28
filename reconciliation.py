import pandas as pd


def reconcile(issued: pd.DataFrame, cleared: pd.DataFrame) -> dict:
    issued = issued.copy()
    cleared = cleared.copy() if not cleared.empty else pd.DataFrame()

    issued["check_number"] = issued["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    issued["amount"] = issued["amount"].astype(float).round(2)
    issued["payment_date"] = pd.to_datetime(issued["payment_date"])

    if not cleared.empty:
        cleared["check_number"] = cleared["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        cleared["amount"] = cleared["amount"].astype(float).round(2)
        cleared["date"] = pd.to_datetime(cleared["date"])

    today = pd.Timestamp.today().normalize()

    # ── Outstanding: issued checks with no matching check number in cleared ──
    if not cleared.empty:
        cleared_numbers = set(cleared["check_number"])
        outstanding = issued[~issued["check_number"].isin(cleared_numbers)].copy()
    else:
        outstanding = issued.copy()

    outstanding["days_outstanding"] = (today - outstanding["payment_date"]).dt.days

    # ── Amount mismatches: matched by check number but amounts differ ──
    if not cleared.empty:
        matched = issued.merge(
            cleared[["check_number", "amount", "date", "status"]].rename(columns={
                "amount": "cleared_amount",
                "date": "cleared_date",
                "status": "cleared_status",
            }),
            on="check_number",
            how="inner",
        )
        amount_mismatches = matched[abs(matched["amount"] - matched["cleared_amount"]) > 0.01].copy()
        amount_mismatches["variance"] = (amount_mismatches["cleared_amount"] - amount_mismatches["amount"]).round(2)
    else:
        amount_mismatches = pd.DataFrame()

    # ── Ghost checks: cleared by bank but never issued ──
    if not cleared.empty:
        issued_numbers = set(issued["check_number"])
        ghost_checks = cleared[~cleared["check_number"].isin(issued_numbers)].copy()
    else:
        ghost_checks = pd.DataFrame()

    # ── Long outstanding: not cleared and issued 90+ days ago ──
    long_outstanding = outstanding[outstanding["days_outstanding"] >= 90].copy()

    stats = {
        "total_issued": len(issued),
        "total_cleared": len(cleared) if not cleared.empty else 0,
        "total_outstanding": len(outstanding),
        "outstanding_amount": outstanding["amount"].sum(),
        "issued_amount": issued["amount"].sum(),
        "cleared_amount": cleared["amount"].sum() if not cleared.empty else 0.0,
        "amount_mismatches": len(amount_mismatches),
        "ghost_checks": len(ghost_checks),
        "long_outstanding_count": len(long_outstanding),
    }

    return {
        "outstanding": outstanding,
        "discrepancies": {
            "amount_mismatches": amount_mismatches,
            "ghost_checks": ghost_checks,
            "long_outstanding": long_outstanding,
        },
        "stats": stats,
    }
