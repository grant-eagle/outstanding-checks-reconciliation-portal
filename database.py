import streamlit as st
import pandas as pd
from supabase import create_client, Client


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
    out = df.copy()
    out["payment_date"] = pd.to_datetime(out["payment_date"]).dt.strftime("%Y-%m-%d")
    out["check_number"] = out["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["amount"] = _clean_amount(out["amount"])
    return out


def _normalize_cleared(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["check_number"] = out["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["amount"] = _clean_amount(out["amount"])
    out["status"] = out["status"].astype(str).str.strip()
    return out


def upsert_issued_checks(df: pd.DataFrame, subsidiary: str) -> dict:
    client = _client()
    df = _normalize_issued(df)
    df["subsidiary"] = subsidiary

    existing_raw = client.table("issued_checks") \
        .select("payment_date,check_number,amount,subsidiary") \
        .eq("subsidiary", subsidiary) \
        .execute()

    if existing_raw.data:
        existing = _normalize_issued(pd.DataFrame(existing_raw.data))
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

    client.table("issued_checks").insert(new_rows.to_dict("records")).execute()
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def upsert_cleared_checks(df: pd.DataFrame, subsidiary: str) -> dict:
    client = _client()
    df = _normalize_cleared(df)
    df["subsidiary"] = subsidiary

    existing_raw = client.table("cleared_checks") \
        .select("date,check_number,amount,status,subsidiary") \
        .eq("subsidiary", subsidiary) \
        .execute()

    if existing_raw.data:
        existing = _normalize_cleared(pd.DataFrame(existing_raw.data))
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

    client.table("cleared_checks").insert(new_rows.to_dict("records")).execute()
    return {"inserted": len(new_rows), "skipped": len(df) - len(new_rows)}


def get_issued_checks(subsidiary: str) -> pd.DataFrame:
    result = _client().table("issued_checks").select("*").eq("subsidiary", subsidiary).execute()
    return pd.DataFrame(result.data) if result.data else pd.DataFrame()


def get_cleared_checks(subsidiary: str) -> pd.DataFrame:
    result = _client().table("cleared_checks").select("*").eq("subsidiary", subsidiary).execute()
    return pd.DataFrame(result.data) if result.data else pd.DataFrame()
