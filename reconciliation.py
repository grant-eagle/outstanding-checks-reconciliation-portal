import pandas as pd


def reconcile(
    issued: pd.DataFrame,
    cleared: pd.DataFrame,
    seed: pd.DataFrame = None,
    voided: pd.DataFrame = None,
) -> dict:
    issued = issued.copy()
    cleared = cleared.copy() if not cleared.empty else pd.DataFrame()
    seed = seed.copy() if seed is not None and not seed.empty else pd.DataFrame()
    voided = voided.copy() if voided is not None and not voided.empty else pd.DataFrame()

    def normalize_checks(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().reset_index(drop=True)
        df["check_number"] = df["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        df["amount"] = df["amount"].astype(float).round(2)
        df["payment_date"] = pd.to_datetime(df["payment_date"])
        return df

    issued = normalize_checks(issued)

    if not seed.empty:
        seed = normalize_checks(seed)
        all_checks = pd.concat(
            [seed[["check_number", "payment_date", "amount"]],
             issued[["check_number", "payment_date", "amount"]]],
            ignore_index=True,
        )
    else:
        all_checks = issued[["check_number", "payment_date", "amount"]].copy()

    if not cleared.empty:
        cleared["check_number"] = cleared["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        cleared["amount"] = cleared["amount"].astype(float).round(2)
        cleared["date"] = pd.to_datetime(cleared["date"])

    if not voided.empty:
        voided = normalize_checks(voided)

    today = pd.Timestamp.today().normalize()

    # ── Step 1: Remove bank-cleared checks ──────────────────────────────
    if not cleared.empty:
        cleared_numbers = set(cleared["check_number"])
        outstanding = all_checks[~all_checks["check_number"].isin(cleared_numbers)].copy()
    else:
        outstanding = all_checks.copy()

    # ── Step 2: Process voided checks against outstanding ────────────────
    void_mismatches = pd.DataFrame()
    if not voided.empty:
        voided_lookup = voided[["check_number", "amount"]].rename(columns={"amount": "void_amount"})
        outstanding_with_void = outstanding.merge(voided_lookup, on="check_number", how="left")

        has_void = outstanding_with_void["void_amount"].notna()
        amount_match = has_void & (abs(outstanding_with_void["void_amount"] - outstanding_with_void["amount"]) <= 0.01)
        amount_mismatch = has_void & ~amount_match

        # Flag mismatches
        void_mismatches = outstanding_with_void[amount_mismatch].copy()
        void_mismatches["void_variance"] = (void_mismatches["void_amount"] - void_mismatches["amount"]).round(2)

        # Remove void-cleared checks from outstanding
        outstanding = outstanding_with_void[~amount_match].drop(columns=["void_amount"]).reset_index(drop=True)

    outstanding["days_outstanding"] = (today - outstanding["payment_date"]).dt.days

    # ── Amount mismatches: bank-cleared but amounts differ ───────────────
    if not cleared.empty:
        matched = all_checks.merge(
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

    # ── Ghost checks: cleared by bank but not in any pool ───────────────
    if not cleared.empty:
        all_numbers = set(all_checks["check_number"])
        ghost_checks = cleared[~cleared["check_number"].isin(all_numbers)].copy()
    else:
        ghost_checks = pd.DataFrame()

    long_outstanding = outstanding[outstanding["days_outstanding"] >= 90].copy()

    stats = {
        "total_seed": len(seed),
        "total_issued": len(issued),
        "total_cleared": len(cleared) if not cleared.empty else 0,
        "total_voided": len(voided) if not voided.empty else 0,
        "voided_amount": voided["amount"].sum() if not voided.empty else 0.0,
        "total_outstanding": len(outstanding),
        "outstanding_amount": outstanding["amount"].sum(),
        "seed_amount": seed["amount"].sum() if not seed.empty else 0.0,
        "issued_amount": issued["amount"].sum(),
        "cleared_amount": cleared["amount"].sum() if not cleared.empty else 0.0,
        "amount_mismatches": len(amount_mismatches),
        "ghost_checks": len(ghost_checks),
        "void_mismatches": len(void_mismatches),
        "long_outstanding_count": len(long_outstanding),
    }

    return {
        "outstanding": outstanding,
        "discrepancies": {
            "amount_mismatches": amount_mismatches,
            "ghost_checks": ghost_checks,
            "void_mismatches": void_mismatches,
            "long_outstanding": long_outstanding,
        },
        "stats": stats,
    }
