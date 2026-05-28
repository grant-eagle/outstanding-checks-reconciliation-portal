import streamlit as st
import pandas as pd
from supabase import create_client, Client

BATCH_SIZE = 500


def _client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def _clean_amount(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .str.strip()
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
        existing = _normalize_issued(existing_raw)
        existing["subsidiary"] = subsidiary
        merged = df.merge(
            existing, on=["payment_date", "check_number", "amount", "subsidiary"],
            how="left", indicator=True
        )
        new_rows = df[merged["_merge"] == "left_only"].reset_index(drop=True)
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
        existing = _normalize_cleared(existing_raw)
        existing["subsidiary"] = subsidiary
        merged = df.merge(
            existing, on=["date", "check_number", "amount", "status", "subsidiary"],
            how="left", indicator=True
        )
        new_rows = df[merged["_merge"] == "left_only"].reset_index(drop=True)
    else:
        new_rows = df

    if new_rows.empty:
        return {"inserted": 0, "skipped": len(df)}

    _insert_batched("cleared_checks", new_rows.to_dict("records"))
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def get_date_range(table: str, date_col: str, subsidiary: str) -> str:
    """Return a human-readable date range string for already-uploaded data."""
    client = _client()
    mn = client.table(table).select(date_col).eq("subsidiary", subsidiary).order(date_col).limit(1).execute()
    mx = client.table(table).select(date_col).eq("subsidiary", subsidiary).order(date_col, desc=True).limit(1).execute()
    if not mn.data or not mx.data:
        return None
    min_date = pd.to_datetime(mn.data[0][date_col]).strftime("%m/%d/%Y")
    max_date = pd.to_datetime(mx.data[0][date_col]).strftime("%m/%d/%Y")
    return f"{min_date} – {max_date}"


def get_issued_checks(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("issued_checks", {"subsidiary": subsidiary})


def get_cleared_checks(subsidiary: str) -> pd.DataFrame:
    return _fetch_all("cleared_checks", {"subsidiary": subsidiary})


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
