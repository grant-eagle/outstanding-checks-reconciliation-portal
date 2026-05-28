import io
import streamlit as st
import pandas as pd
import plotly.express as px

def fmt_acct(val: float) -> str:
    """Format a number in accounting style: $1,234.56 or $(1,234.56) for negatives."""
    if pd.isna(val):
        return ""
    if val < 0:
        return f"$({abs(val):,.2f})"
    return f"${val:,.2f}"


def fmt_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%m/%d/%Y")


from database import (
    upsert_issued_checks,
    upsert_cleared_checks,
    upsert_voided_checks,
    upsert_issued_ach,
    upsert_cleared_ach,
    get_issued_checks,
    get_cleared_checks,
    get_voided_checks,
    get_seed_checks,
    get_issued_ach,
    get_cleared_ach,
    load_seed_checks,
    clear_seed_checks,
    get_date_range,
    get_allowed_cycles,
    add_allowed_cycle,
)
from reconciliation import reconcile, reconcile_ach


@st.cache_data(ttl=300, show_spinner=False)
def load_reconciliation_data(subsidiary: str):
    issued = get_issued_checks(subsidiary)
    cleared = get_cleared_checks(subsidiary)
    seed = get_seed_checks(subsidiary)
    voided = get_voided_checks(subsidiary)
    return issued, cleared, seed, voided


@st.cache_data(ttl=300, show_spinner=False)
def cached_date_range(table: str, date_col: str, subsidiary: str):
    return get_date_range(table, date_col, subsidiary)


@st.cache_data(ttl=300, show_spinner=False)
def cached_allowed_cycles(subsidiary: str) -> list:
    return get_allowed_cycles(subsidiary)


@st.cache_data(ttl=300, show_spinner=False)
def load_ach_data(subsidiary: str):
    return get_issued_ach(subsidiary), get_cleared_ach(subsidiary)

st.set_page_config(
    page_title="Check Reconciliation Portal",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Auth ────────────────────────────────────────────────────────────────────
def require_login() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("Check Reconciliation Portal")
    password = st.text_input("Password", type="password", key="pw_input")
    if st.button("Log In"):
        if password == st.secrets.get("APP_PASSWORD", ""):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not require_login():
    st.stop()


# ── Sidebar ─────────────────────────────────────────────────────────────────
subsidiaries = [s.strip() for s in st.secrets.get("SUBSIDIARIES", "Default").split(",")]

st.sidebar.title("Check Reconciliation")
subsidiary = st.sidebar.selectbox("Subsidiary", subsidiaries)
st.sidebar.divider()
page = st.sidebar.radio("", ["Upload Files", "Reconciliation & Dashboard", "Seed Upload (Admin)"])
st.sidebar.divider()
if st.sidebar.button("Log Out"):
    st.session_state.authenticated = False
    st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# PAGE: UPLOAD
# ════════════════════════════════════════════════════════════════════════════
if page == "Upload Files":
    st.title(f"Upload Check Files — {subsidiary}")
    st.caption(
        "Upload CSVs to append new records to each database. "
        "Rows that exactly match existing records are automatically skipped."
    )
    st.info("**Note:** Historical check data from inception through 12/31/2025 is maintained in the seed database. Use the upload sections below for data from 1/1/2026 onwards.")

    col_issued, col_cleared = st.columns(2)

    # ── Issued Checks ────────────────────────────────────────────────────
    with col_issued:
        st.subheader("Issued Checks")
        st.caption("Required columns: **Payment Date · Payment Number · Payment Type · Payment Impact**")
        issued_range = cached_date_range("issued_checks", "payment_date", subsidiary)
        if issued_range:
            st.info(f"Data already uploaded: **{issued_range}**")
        else:
            st.info("No issued checks uploaded yet.")
        issued_file = st.file_uploader("Choose CSV", type="csv", key="up_issued")

        if issued_file:
            try:
                raw = pd.read_csv(issued_file)
                required = ["Payment Date", "Payment Number", "Payment Type", "Payment Impact", "Cycle Identifier"]
                missing = [c for c in required if c not in raw.columns]
                if missing:
                    st.error(f"Missing columns: {', '.join(missing)}")
                else:
                    # Filter checks and non-zero payment numbers
                    pre_validate = raw[raw["Payment Type"].str.strip().str.lower() == "check"].copy()
                    pre_validate = pre_validate[
                        pre_validate["Payment Number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True) != "0"
                    ].copy()

                    # Validate Cycle Identifiers
                    allowed_cycles = cached_allowed_cycles(subsidiary)
                    upload_cycles = pre_validate["Cycle Identifier"].astype(str).str.strip().unique().tolist()
                    unknown_cycles = [c for c in upload_cycles if c not in allowed_cycles]

                    cycle_decisions = {}
                    if unknown_cycles:
                        st.warning(f"{len(unknown_cycles)} unrecognized Payment Cycle(s) found in this file.")
                        for cycle in sorted(unknown_cycles):
                            count = len(pre_validate[pre_validate["Cycle Identifier"].astype(str).str.strip() == cycle])
                            st.markdown(f"**{cycle}** — {count:,} rows")
                            st.caption(
                                f'Is **"{cycle}"** a new Payment Cycle for **{subsidiary}**? '
                                f'Or should it be removed from this upload?'
                            )
                            decision = st.radio(
                                "",
                                ["Add to this subsidiary", "Remove from upload"],
                                key=f"cycle_decision_{cycle}",
                                horizontal=True,
                            )
                            cycle_decisions[cycle] = decision
                        st.divider()

                    # Apply "remove" decisions
                    working = pre_validate.copy()
                    for cycle, decision in cycle_decisions.items():
                        if decision == "Remove from upload":
                            working = working[working["Cycle Identifier"].astype(str).str.strip() != cycle]

                    # Aggregate and prepare for upload
                    filtered = working[["Payment Date", "Payment Number", "Payment Impact"]].rename(columns={
                        "Payment Date": "payment_date",
                        "Payment Number": "check_number",
                        "Payment Impact": "amount",
                    })
                    filtered["amount"] = pd.to_numeric(
                        filtered["amount"].astype(str).str.replace(r"[\$,]", "", regex=True), errors="coerce"
                    )
                    filtered = filtered.groupby(["check_number", "payment_date"], as_index=False)["amount"].sum()

                    # ACH: aggregate by payment date from same raw file
                    ach_rows = raw[raw["Payment Type"].astype(str).str.strip().str.lower() == "ach"].copy()
                    ach_filtered = pd.DataFrame()
                    if not ach_rows.empty:
                        ach_filtered = ach_rows[["Payment Date", "Payment Impact"]].rename(columns={
                            "Payment Date": "payment_date",
                            "Payment Impact": "amount",
                        })
                        ach_filtered["amount"] = pd.to_numeric(
                            ach_filtered["amount"].astype(str).str.replace(r"[\$,]", "", regex=True), errors="coerce"
                        )
                        ach_filtered = ach_filtered.groupby("payment_date", as_index=False)["amount"].sum()

                    st.info(
                        f"{len(filtered):,} checks found in file (checks already in the database will be skipped automatically on upload)"
                        + (f" · {len(ach_filtered):,} ACH batch dates also found" if not ach_filtered.empty else "")
                    )
                    st.dataframe(filtered.head(10), use_container_width=True)

                    if st.button("Add to Issued Checks Database", type="primary", key="btn_issued"):
                        for cycle, decision in cycle_decisions.items():
                            if decision == "Add to this subsidiary":
                                add_allowed_cycle(subsidiary, cycle)
                        if cycle_decisions:
                            st.cache_data.clear()

                        with st.spinner("Saving…"):
                            result = upsert_issued_checks(filtered, subsidiary)
                            ach_result = upsert_issued_ach(ach_filtered, subsidiary) if not ach_filtered.empty else None
                        msg = f"{result['inserted']:,} checks added · {result['skipped']:,} duplicates skipped"
                        if ach_result:
                            msg += f" · {ach_result['inserted']:,} ACH batches added"
                        st.success(msg)
            except Exception as exc:
                st.error(f"Could not read file: {exc}")

    # ── Cleared Checks ───────────────────────────────────────────────────
    with col_cleared:
        st.subheader("Cleared Checks (Bank)")
        st.caption("Required columns: **Post Date · Transaction Name - BAI · Customer Reference · Status · Amount**")
        cleared_range = cached_date_range("cleared_checks", "date", subsidiary)
        if cleared_range:
            st.info(f"Data already uploaded: **{cleared_range}**")
        else:
            st.info("No cleared checks uploaded yet.")
        cleared_file = st.file_uploader("Choose CSV", type="csv", key="up_cleared")

        if cleared_file:
            try:
                raw = pd.read_csv(cleared_file)
                required = ["Post Date", "Transaction Name - BAI", "Customer Reference", "Status", "Amount"]
                missing = [c for c in required if c not in raw.columns]
                if missing:
                    st.error(f"Missing columns: {', '.join(missing)}")
                else:
                    filtered = raw[
                        raw["Transaction Name - BAI"].astype(str).str.strip().str.lower().str.contains("check", na=False)
                    ].copy()
                    filtered = filtered[["Post Date", "Transaction Name - BAI", "Customer Reference", "Status", "Amount"]].rename(columns={
                        "Post Date": "date",
                        "Transaction Name - BAI": "description",
                        "Customer Reference": "check_number",
                        "Status": "status",
                        "Amount": "amount",
                    })
                    filtered["amount"] = (
                        filtered["amount"].astype(str).str.strip()
                        .str.replace(r"[\$,\s]", "", regex=True)
                        .str.replace(r"^\((.+)\)$", r"-\1", regex=True)
                        .astype(float).abs()
                    )

                    # ACH: filter for PREAUTHORIZED DEBIT rows from same raw file
                    ach_bank_rows = raw[
                        raw["Transaction Detail"].astype(str).str.strip().str.contains(
                            "PREAUTHORIZED DEBIT CURATIVETPALF", na=False
                        )
                    ].copy()
                    ach_bank_filtered = pd.DataFrame()
                    if not ach_bank_rows.empty:
                        ach_bank_filtered = ach_bank_rows[["Post Date", "Amount"]].rename(columns={
                            "Post Date": "date",
                            "Amount": "amount",
                        })
                        ach_bank_filtered["amount"] = (
                            ach_bank_filtered["amount"].astype(str).str.strip()
                            .str.replace(r"[\$,\s]", "", regex=True)
                            .str.replace(r"^\((.+)\)$", r"-\1", regex=True)
                            .astype(float).abs()
                        )
                        ach_bank_filtered = ach_bank_filtered.groupby("date", as_index=False)["amount"].sum()

                    st.info(
                        f"{len(filtered):,} check rows found ({len(raw) - len(filtered):,} non-check rows excluded)"
                        + (f" · {len(ach_bank_filtered):,} ACH clearing rows also found" if not ach_bank_filtered.empty else "")
                    )
                    st.dataframe(filtered.head(10), use_container_width=True)

                    if st.button("Add to Cleared Checks Database", type="primary", key="btn_cleared"):
                        with st.spinner("Saving…"):
                            result = upsert_cleared_checks(filtered, subsidiary)
                            ach_result = upsert_cleared_ach(ach_bank_filtered, subsidiary) if not ach_bank_filtered.empty else None
                        msg = f"{result['inserted']:,} checks added · {result['skipped']:,} duplicates skipped"
                        if ach_result:
                            msg += f" · {ach_result['inserted']:,} ACH clearings added"
                        st.success(msg)
            except Exception as exc:
                st.error(f"Could not read file: {exc}")

    # ── Voided Checks ────────────────────────────────────────────────────
    st.divider()
    st.subheader("Voided Checks")
    st.caption("Required columns: **Payment Date · Payment Number · Payment Type · Payment Impact**")
    voided_range = cached_date_range("voided_checks", "payment_date", subsidiary)
    if voided_range:
        st.info(f"Data already uploaded: **{voided_range}**")
    else:
        st.info("No voided checks uploaded yet.")
    voided_file = st.file_uploader("Choose CSV", type="csv", key="up_voided")

    if voided_file:
        try:
            raw = pd.read_csv(voided_file)
            required = ["Payment Date", "Payment Number", "Payment Type", "Payment Impact"]
            missing = [c for c in required if c not in raw.columns]
            if missing:
                st.error(f"Missing columns: {', '.join(missing)}")
            else:
                filtered = raw[raw["Payment Type"].str.strip().str.lower() == "check"].copy()
                filtered = filtered[filtered["Payment Number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True) != "0"].copy()
                filtered = filtered[["Payment Date", "Payment Number", "Payment Impact"]].rename(columns={
                    "Payment Date": "payment_date",
                    "Payment Number": "check_number",
                    "Payment Impact": "amount",
                })
                filtered["amount"] = pd.to_numeric(filtered["amount"].astype(str).str.replace(r"[\$,]", "", regex=True), errors="coerce")
                filtered = filtered.groupby(["check_number", "payment_date"], as_index=False)["amount"].sum()

                st.info(f"{len(filtered):,} unique voided checks found")
                st.dataframe(filtered.head(10), use_container_width=True)

                if st.button("Add to Voided Checks Database", type="primary", key="btn_voided"):
                    with st.spinner("Saving…"):
                        result = upsert_voided_checks(filtered, subsidiary)
                    st.success(f"{result['inserted']:,} rows added · {result['skipped']:,} duplicates skipped")
        except Exception as exc:
            st.error(f"Could not read file: {exc}")



# ════════════════════════════════════════════════════════════════════════════
# PAGE: RECONCILIATION & DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
elif page == "Reconciliation & Dashboard":
    st.title(f"Reconciliation & Dashboard — {subsidiary}")

    col_refresh, col_asof, _ = st.columns([1, 2, 3])
    if col_refresh.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    as_of_date = col_asof.date_input(
        "As of Date",
        value=pd.Timestamp.today().date(),
        help="Show the outstanding balance as of this date. Issued and voided checks are filtered by payment date; cleared checks by clearing date.",
    )
    as_of_ts = pd.Timestamp(as_of_date)

    with st.spinner("Loading data…"):
        issued, cleared, seed, voided = load_reconciliation_data(subsidiary)

    if issued.empty and seed.empty:
        st.warning("No check data in the database yet. Go to **Upload Files** or **Seed Upload (Admin)** to get started.")
        st.stop()

    # Apply as-of-date filter
    if not issued.empty:
        issued = issued[pd.to_datetime(issued["payment_date"]) <= as_of_ts].copy()
    if not cleared.empty:
        cleared = cleared[pd.to_datetime(cleared["date"]) <= as_of_ts].copy()
    if not voided.empty:
        voided = voided[pd.to_datetime(voided["payment_date"]) <= as_of_ts].copy()
    # seed is a fixed historical baseline — no date filter applied

    st.caption(f"Showing outstanding balance as of **{as_of_date.strftime('%B %d, %Y')}**")

    results = reconcile(issued, cleared, seed, voided)
    stats = results["stats"]
    outstanding = results["outstanding"]
    disc = results["discrepancies"]

    # ── KPI row ──────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Seed Checks (Historical)", f"{stats['total_seed']:,}", fmt_acct(stats['seed_amount']))
    k2.metric("Issued Checks", f"{stats['total_issued']:,}", fmt_acct(stats['issued_amount']))
    k3.metric("Cleared Checks", f"{stats['total_cleared']:,}", fmt_acct(stats['cleared_amount']))
    k4.metric("Voided Checks", f"{stats['total_voided']:,}", fmt_acct(stats['voided_amount']))
    k5.metric("Outstanding Checks", f"{stats['total_outstanding']:,}", fmt_acct(stats['outstanding_amount']))
    k6.metric("Total Discrepancies", f"{stats['amount_mismatches'] + stats['ghost_checks']:,}", delta_color="inverse")

    st.divider()

    # ── Outstanding checks table + download ──────────────────────────────
    st.subheader("Outstanding Checks")

    if outstanding.empty:
        st.success("All issued checks have cleared.")
    else:
        display = (
            outstanding[["check_number", "payment_date", "amount", "days_outstanding"]]
            .sort_values("payment_date")
            .copy()
        )
        display.columns = ["Check Number", "Payment Date", "Amount", "Days Outstanding"]
        display["Payment Date"] = fmt_date(display["Payment Date"])
        display["Amount"] = display["Amount"].map(fmt_acct)

        st.dataframe(display, use_container_width=True, hide_index=True)

        buf = io.StringIO()
        display.to_csv(buf, index=False)
        st.download_button(
            label="Download Outstanding Checks CSV",
            data=buf.getvalue(),
            file_name=f"outstanding_checks_{subsidiary.replace(' ', '_')}_as_of_{as_of_date.strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="primary",
        )

    st.divider()

    # ── Discrepancy tabs ─────────────────────────────────────────────────
    st.subheader("Discrepancy Dashboard")

    tab1, tab2, tab3, tab4 = st.tabs([
        f"Amount Mismatches  ({stats['amount_mismatches']})",
        f"Unrecognized Cleared Checks  ({stats['ghost_checks']})",
        f"Void Amount Mismatches  ({stats['void_mismatches']})",
        f"Long Outstanding 90+ Days  ({stats['long_outstanding_count']})",
    ])

    with tab1:
        mm = disc["amount_mismatches"]
        if mm.empty:
            st.success("No amount mismatches.")
        else:
            st.caption("These checks were found in both databases but the amounts do not match.")
            display = mm[["check_number", "payment_date", "amount", "cleared_amount", "variance", "cleared_date", "cleared_status"]].copy()
            display.columns = ["Check #", "Issue Date", "Issued Amt", "Cleared Amt", "Variance", "Cleared Date", "Status"]
            display["Issue Date"] = fmt_date(display["Issue Date"])
            display["Cleared Date"] = fmt_date(display["Cleared Date"])

            def color_variance(val):
                color = "#ffcccc" if val < 0 else "#fff3cc" if val > 0 else ""
                return f"background-color: {color}"

            st.dataframe(
                display.style
                    .map(color_variance, subset=["Variance"])
                    .format({"Issued Amt": fmt_acct, "Cleared Amt": fmt_acct, "Variance": fmt_acct}),
                use_container_width=True,
                hide_index=True,
            )

            fig = px.bar(
                display,
                x="Check #",
                y="Variance",
                title="Variance per Check (Cleared Amount − Issued Amount)",
                color="Variance",
                color_continuous_scale="RdYlGn",
                labels={"Variance": "$ Variance"},
            )
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        gc = disc["ghost_checks"]
        if gc.empty:
            st.success("No unrecognized cleared checks.")
        else:
            st.caption("These checks appear in the bank data but have no matching issued check.")
            display = gc[["check_number", "date", "amount", "description", "status"]].copy()
            display.columns = ["Check #", "Cleared Date", "Amount", "Description", "Status"]
            display["Cleared Date"] = fmt_date(display["Cleared Date"])
            display["Amount"] = display["Amount"].map(fmt_acct)
            st.dataframe(display, use_container_width=True, hide_index=True)

    with tab3:
        vm = disc["void_mismatches"]
        if vm.empty:
            st.success("No void amount mismatches.")
        else:
            st.caption("These checks were found in the voided file but the void amount does not match the outstanding amount.")
            display = vm[["check_number", "payment_date", "amount", "void_amount", "void_variance"]].copy()
            display.columns = ["Check #", "Issue Date", "Outstanding Amt", "Void Amt", "Variance"]
            display["Issue Date"] = fmt_date(display["Issue Date"])

            def color_void_variance(val):
                color = "#ffcccc" if val < 0 else "#fff3cc" if val > 0 else ""
                return f"background-color: {color}"

            st.dataframe(
                display.style
                    .map(color_void_variance, subset=["Variance"])
                    .format({"Outstanding Amt": fmt_acct, "Void Amt": fmt_acct, "Variance": fmt_acct}),
                use_container_width=True,
                hide_index=True,
            )

    with tab4:
        lo = disc["long_outstanding"]
        if lo.empty:
            st.success("No checks outstanding for 90+ days.")
        else:
            st.caption("Issued checks that have not cleared within 90 days.")
            display = (
                lo[["check_number", "payment_date", "amount", "days_outstanding"]]
                .sort_values("days_outstanding", ascending=False)
                .copy()
            )
            display.columns = ["Check #", "Issue Date", "Amount", "Days Outstanding"]
            display["Issue Date"] = fmt_date(display["Issue Date"])
            display["Amount"] = display["Amount"].map(fmt_acct)
            st.dataframe(display, use_container_width=True, hide_index=True)

            fig = px.histogram(
                lo,
                x="days_outstanding",
                nbins=20,
                title="Distribution of Days Outstanding (90+ day checks)",
                labels={"days_outstanding": "Days Outstanding"},
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── ACH Reconciliation ───────────────────────────────────────────────
    st.divider()
    st.subheader("ACH Batch Reconciliation")
    st.caption("Issued ACH totals are matched against bank clearings within a ±7 day window.")

    with st.spinner("Loading ACH data…"):
        issued_ach, cleared_ach = load_ach_data(subsidiary)

    if not issued_ach.empty:
        issued_ach = issued_ach[pd.to_datetime(issued_ach["payment_date"]) <= as_of_ts].copy()
    if not cleared_ach.empty:
        cleared_ach = cleared_ach[pd.to_datetime(cleared_ach["date"]) <= as_of_ts].copy()

    if issued_ach.empty:
        st.info("No issued ACH data uploaded yet. Go to **Upload Files** to get started.")
    else:
        ach = reconcile_ach(issued_ach, cleared_ach)
        ach_stats = ach["stats"]

        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Issued ACH Batches", f"{ach_stats['total_issued_ach']:,}", fmt_acct(ach_stats['issued_ach_amount']))
        a2.metric("Matched", f"{ach_stats['total_matched_ach']:,}")
        a3.metric("Outstanding ACH", f"{ach_stats['total_outstanding_ach']:,}", fmt_acct(ach_stats['outstanding_ach_amount']))
        a4.metric("Unrecognized Bank ACH", f"{ach_stats['unmatched_cleared_count']:,}")

        st.divider()

        ach_tab1, ach_tab2, ach_tab3 = st.tabs([
            f"Outstanding ACH Batches  ({ach_stats['total_outstanding_ach']})",
            f"Matched ACH  ({ach_stats['total_matched_ach']})",
            f"Unrecognized Bank ACH  ({ach_stats['unmatched_cleared_count']})",
        ])

        with ach_tab1:
            if ach["outstanding"].empty:
                st.success("All issued ACH batches have been matched.")
            else:
                display = ach["outstanding"].copy()
                display.columns = ["Payment Date", "Amount"]
                display["Payment Date"] = fmt_date(display["Payment Date"])
                display["Amount"] = display["Amount"].map(fmt_acct)
                st.dataframe(display, use_container_width=True, hide_index=True)

                buf = io.StringIO()
                display.to_csv(buf, index=False)
                st.download_button(
                    label="Download Outstanding ACH CSV",
                    data=buf.getvalue(),
                    file_name=f"outstanding_ach_{subsidiary.replace(' ', '_')}_{pd.Timestamp.today().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

        with ach_tab2:
            if ach["matched"].empty:
                st.info("No matched ACH batches yet.")
            else:
                display = ach["matched"].copy()
                display.columns = ["Payment Date", "Issued Amount", "Cleared Date", "Cleared Amount", "Days Difference", "Match Type"]
                display["Payment Date"] = fmt_date(display["Payment Date"])
                display["Cleared Date"] = fmt_date(display["Cleared Date"])
                display["Issued Amount"] = display["Issued Amount"].map(fmt_acct)
                display["Cleared Amount"] = display["Cleared Amount"].map(fmt_acct)
                st.dataframe(display, use_container_width=True, hide_index=True)

        with ach_tab3:
            if ach["unmatched_cleared"].empty:
                st.success("No unrecognized bank ACH entries.")
            else:
                st.caption("Bank ACH clearings with no matching issued ACH batch within ±7 days.")
                display = ach["unmatched_cleared"][["date", "amount"]].copy()
                display.columns = ["Cleared Date", "Amount"]
                display["Cleared Date"] = fmt_date(display["Cleared Date"])
                display["Amount"] = display["Amount"].map(fmt_acct)
                st.dataframe(display, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# PAGE: SEED UPLOAD (ADMIN)
# ════════════════════════════════════════════════════════════════════════════
elif page == "Seed Upload (Admin)":
    st.title(f"Seed Upload (Admin) — {subsidiary}")
    st.caption(
        "Load the 12/31/2025 historical outstanding checks as the baseline for this subsidiary. "
        "Once uploaded, seed records cannot be modified or deleted through the app."
    )

    admin_pw = st.text_input("Admin Password", type="password", key="admin_pw")
    if not admin_pw:
        st.stop()
    if admin_pw != st.secrets.get("ADMIN_PASSWORD", ""):
        st.error("Incorrect admin password.")
        st.stop()

    existing_seed = get_seed_checks(subsidiary)
    if not existing_seed.empty:
        st.info(
            f"**{subsidiary}** already has {len(existing_seed):,} seed records "
            f"totalling {fmt_acct(existing_seed['amount'].sum())}."
        )
        st.dataframe(
            existing_seed[["check_number", "payment_date", "amount"]]
            .rename(columns={"check_number": "Check #", "payment_date": "Payment Date", "amount": "Amount"})
            .assign(**{"Payment Date": lambda d: fmt_date(d["Payment Date"]), "Amount": lambda d: d["Amount"].map(fmt_acct)}),
            use_container_width=True,
            hide_index=True,
        )
        st.divider()
        st.subheader("Clear Seed Data")
        st.warning(f"This will permanently delete all {len(existing_seed):,} seed records for **{subsidiary}**. You can then re-upload a corrected file.")
        if st.button("Clear Seed Data for This Subsidiary", type="primary"):
            with st.spinner("Clearing…"):
                clear_seed_checks(subsidiary)
            st.success("Seed data cleared. You may now upload a new file.")
            st.rerun()
        st.stop()

    st.subheader("Upload Historical Outstanding Checks (as of 12/31/2025)")
    st.caption(
        "Required columns: **check number · Check Batch Date · Export Type · Outstanding Check Amount**  \n"
        "Rows where Export Type = **Check** or **HARDCOPY** are imported. ACH and EFT rows are excluded."
    )

    seed_file = st.file_uploader("Choose CSV", type="csv", key="up_seed")

    if seed_file:
        try:
            raw = pd.read_csv(seed_file)
            required = ["check number", "Check Batch Date", "Export Type", "Outstanding Check Amount"]
            missing = [c for c in required if c not in raw.columns]
            if missing:
                st.error(f"Missing columns: {', '.join(missing)}")
            else:
                filtered = raw[raw["Export Type"].astype(str).str.strip().str.lower().isin(["hardcopy", "check"])].copy()
                filtered = filtered[["check number", "Check Batch Date", "Outstanding Check Amount"]].rename(columns={
                    "check number": "check_number",
                    "Check Batch Date": "payment_date",
                    "Outstanding Check Amount": "amount",
                })
                filtered = filtered[
                    filtered["check_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True) != "0"
                ].copy()
                filtered["amount"] = pd.to_numeric(filtered["amount"].astype(str).str.replace(r"[\$,]", "", regex=True), errors="coerce")
                filtered = filtered.groupby(["check_number", "payment_date"], as_index=False)["amount"].sum()

                pre_agg = raw[raw["Export Type"].astype(str).str.strip().str.lower().isin(["hardcopy", "check"])].copy()
                ach_excluded = len(raw) - len(pre_agg)
                consolidated = len(pre_agg) - len(filtered)
                st.info(
                    f"{len(filtered):,} unique checks found · "
                    f"{consolidated:,} duplicate lines consolidated · "
                    f"{ach_excluded:,} ACH/EFT rows excluded"
                )
                st.dataframe(filtered.head(10), use_container_width=True)

                st.warning("This action cannot be undone through the app. Confirm before proceeding.")
                if st.button("Load Seed Data", type="primary"):
                    with st.spinner("Loading seed data…"):
                        result = load_seed_checks(filtered, subsidiary)
                    st.success(f"{result['inserted']:,} historical checks loaded for {subsidiary}.")
        except Exception as exc:
            st.error(f"Could not read file: {exc}")
