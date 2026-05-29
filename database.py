import streamlit as st
import pandas as pd
from supabase import create_client, Client

BATCH_SIZE = 500


def _client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def _clean_amount(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"[\$,\s]", "", regex=True)
        .str.replace(r"^\((.+)\)$", r"-\1", regex=True)  # $(189.07) → -189.07
        .astype(float)
        .round(2)
    )


def _normalize_issued(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().reset_index(drop=True)
    out["payment_date"] = pd.to_datetime(out["payment_date"]).dt.strftime("%Y-%m-%d")
    out["check_number"] = out["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["amount"] = _clean_amount(out["amount"])
    return out


def _normalize_cleared(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().reset_index(drop=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["check_number"] = out["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["amount"] = _clean_amount(out["amount"])
    out["status"] = out["status"].astype(str).str.strip()
    return out


def _fetch_all(table: str, filters: dict) -> pd.DataFrame:
    """Fetch all rows from a table using pagination to bypass the 1000-row default limit."""
    client = _client()
    rows = []
    start = 0

    while True:
        query = client.table(table).select("*")
        for col, val in filters.items():
            query = query.eq(col, val)
        result = query.range(start, start + BATCH_SIZE - 1).execute()

        if not result.data:
            break
        rows.extend(result.data)
        if len(result.data) < BATCH_SIZE:
            break
        start += BATCH_SIZE

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _insert_batched(table: str, records: list) -> None:
    """Insert records in batches to avoid request size limits."""
    client = _client()
    for i in range(0, len(records), BATCH_SIZE):
        client.table(table).insert(records[i:i + BATCH_SIZE]).execute()


def upsert_issued_checks(df: pd.DataFrame, subsidiary: str) -> dict:
    df = _normalize_issued(df)
    df["subsidiary"] = subsidiary

    existing_raw = _fetch_all("issued_checks", {"subsidiary": subsidiary})
    if not existing_raw.empty:
        existing_numbers = set(
            existing_raw["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        )
        new_rows = df[~df["check_number"].isin(existing_numbers)].reset_index(drop=True)
    else:
        new_rows = df

    if new_rows.empty:
        return {"inserted": 0, "skipped": len(df)}

    _insert_batched("issued_checks", new_rows.to_dict("records"))
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def upsert_cleared_checks(df: pd.DataFrame, subsidiary: str) -> dict:
    df = _normalize_cleared(df)
    df["subsidiary"] = subsidiary

    existing_raw = _fetch_all("cleared_checks", {"subsidiary": subsidiary})
    if not existing_raw.empty:
        existing_numbers = set(
            existing_raw["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        )
        new_rows = df[~df["check_number"].isin(existing_numbers)].reset_index(drop=True)
    else:
        new_rows = df

    if new_rows.empty:
        return {"inserted": 0, "skipped": len(df)}

    _insert_batched("cleared_checks", new_rows.to_dict("records"))
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def get_issued_ach(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("issued_ach", {"subsidiary": subsidiary})


def get_cleared_ach(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("cleared_ach", {"subsidiary": subsidiary})


def upsert_issued_ach(df: pd.DataFrame, subsidiary: str) -> dict:
    df = df.copy().reset_index(drop=True)
    df["payment_date"] = pd.to_datetime(df["payment_date"]).dt.strftime("%Y-%m-%d")
    df["amount"] = _clean_amount(df["amount"])
    df["subsidiary"] = subsidiary

    existing_raw = _fetch_all("issued_ach", {"subsidiary": subsidiary})
    if not existing_raw.empty:
        existing = existing_raw.copy()
        existing["payment_date"] = pd.to_datetime(existing["payment_date"]).dt.strftime("%Y-%m-%d")
        existing["amount"] = existing["amount"].astype(float).round(2)
        existing["subsidiary"] = subsidiary
        merged = df.merge(existing, on=["payment_date", "amount", "subsidiary"], how="left", indicator=True)
        new_rows = df[merged["_merge"] == "left_only"].reset_index(drop=True)
    else:
        new_rows = df

    if new_rows.empty:
        return {"inserted": 0, "skipped": len(df)}
    _insert_batched("issued_ach", new_rows.to_dict("records"))
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def upsert_cleared_ach(df: pd.DataFrame, subsidiary: str) -> dict:
    df = df.copy().reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["amount"] = _clean_amount(df["amount"])
    df["subsidiary"] = subsidiary

    existing_raw = _fetch_all("cleared_ach", {"subsidiary": subsidiary})
    if not existing_raw.empty:
        existing = existing_raw.copy()
        existing["date"] = pd.to_datetime(existing["date"]).dt.strftime("%Y-%m-%d")
        existing["amount"] = existing["amount"].astype(float).round(2)
        existing["subsidiary"] = subsidiary
        merged = df.merge(existing, on=["date", "amount", "subsidiary"], how="left", indicator=True)
        new_rows = df[merged["_merge"] == "left_only"].reset_index(drop=True)
    else:
        new_rows = df

    if new_rows.empty:
        return {"inserted": 0, "skipped": len(df)}
    _insert_batched("cleared_ach", new_rows.to_dict("records"))
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def get_allowed_cycles(subsidiary: str) -> list:
    result = _client().table("subsidiary_cycles").select("cycle_identifier").eq("subsidiary", subsidiary).execute()
    return [r["cycle_identifier"] for r in result.data] if result.data else []


def add_allowed_cycle(subsidiary: str, cycle_identifier: str) -> None:
    try:
        _client().table("subsidiary_cycles").insert({
            "subsidiary": subsidiary,
            "cycle_identifier": cycle_identifier,
        }).execute()
    except Exception:
        pass  # Already exists — unique constraint


def get_date_range(table: str, date_col: str, subsidiary: str) -> str:
    """Return a human-readable date range string for already-uploaded data."""
    try:
        client = _client()
        mn = client.table(table).select(date_col).eq("subsidiary", subsidiary).order(date_col).limit(1).execute()
        mx = client.table(table).select(date_col).eq("subsidiary", subsidiary).order(date_col, desc=True).limit(1).execute()
        if not mn.data or not mx.data:
            return None
        min_date = pd.to_datetime(mn.data[0][date_col]).strftime("%m/%d/%Y")
        max_date = pd.to_datetime(mx.data[0][date_col]).strftime("%m/%d/%Y")
        return f"{min_date} – {max_date}"
    except Exception:
        return None


def get_issued_checks(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("issued_checks", {"subsidiary": subsidiary})


def get_cleared_checks(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("cleared_checks", {"subsidiary": subsidiary})


def get_voided_checks(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("voided_checks", {"subsidiary": subsidiary})


def upsert_voided_checks(df: pd.DataFrame, subsidiary: str) -> dict:
    df = _normalize_issued(df)
    df["subsidiary"] = subsidiary

    existing_raw = _fetch_all("voided_checks", {"subsidiary": subsidiary})
    if not existing_raw.empty:
        existing_numbers = set(
            existing_raw["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        )
        new_rows = df[~df["check_number"].isin(existing_numbers)].reset_index(drop=True)
    else:
        new_rows = df

    if new_rows.empty:
        return {"inserted": 0, "skipped": len(df)}

    _insert_batched("voided_checks", new_rows.to_dict("records"))
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def get_seed_checks(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("seed_checks", {"subsidiary": subsidiary})


def clear_seed_checks(subsidiary: str) -> None:
    _client().table("seed_checks").delete().eq("subsidiary", subsidiary).execute()


def load_seed_checks(df: pd.DataFrame, subsidiary: str) -> dict:
    """Insert seed checks for a subsidiary. Protected at DB level — no delete via anon key."""
    df = df.copy()
    df["check_number"] = df["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["payment_date"] = pd.to_datetime(df["payment_date"]).dt.strftime("%Y-%m-%d")
    df["amount"] = _clean_amount(df["amount"])
    df["subsidiary"] = subsidiary
    _insert_batched("seed_checks", df.to_dict("records"))
    return {"inserted": len(df)}


def get_user_name(email: str) -> str:
    result = _client().table("user_profiles").select("display_name").eq("email", email).execute()
    return result.data[0]["display_name"] if result.data else None


def save_user_name(email: str, display_name: str) -> None:
    _client().table("user_profiles").upsert(
        {"email": email, "display_name": display_name},
        on_conflict="email",
    ).execute()


def get_allowed_accounts(subsidiary: str) -> list:
    result = _client().table("subsidiary_accounts").select("account_number").eq("subsidiary", subsidiary).execute()
    return [r["account_number"] for r in result.data] if result.data else []


def add_allowed_account(subsidiary: str, account_number: str) -> None:
    try:
        _client().table("subsidiary_accounts").insert({
            "subsidiary": subsidiary,
            "account_number": account_number,
        }).execute()
    except Exception:
        pass  # Already exists — unique constraint


def get_annotations(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("discrepancy_annotations", {"subsidiary": subsidiary})


def save_annotations(subsidiary: str, rows: list) -> None:
    """Upsert discrepancy annotations. Each row must have discrepancy_type, check_number, next_steps, notes."""
    if not rows:
        return
    now = pd.Timestamp.utcnow().isoformat()
    records = [
        {
            "subsidiary": subsidiary,
            "discrepancy_type": r["discrepancy_type"],
            "check_number": str(r["check_number"]).strip(),
            "next_steps": r.get("next_steps", "") or "",
            "notes": r.get("notes", "") or "",
            "updated_at": now,
        }
        for r in rows
    ]
    client = _client()
    for i in range(0, len(records), BATCH_SIZE):
        client.table("discrepancy_annotations").upsert(
            records[i:i + BATCH_SIZE],
            on_conflict="subsidiary,discrepancy_type,check_number",
        ).execute()
