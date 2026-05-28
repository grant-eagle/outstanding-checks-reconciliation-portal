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


from database import (
    upsert_issued_checks,
    upsert_cleared_checks,
    get_issued_checks,
    get_cleared_checks,
    get_seed_checks,
    load_seed_checks,
    clear_seed_checks,
    get_date_range,
)
from reconciliation import reconcile

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

    col_issued, col_cleared = st.columns(2)

    # ── Issued Checks ────────────────────────────────────────────────────
    with col_issued:
        st.subheader("Issued Checks")
        st.caption("Required columns: **Payment Date · Payment Number · Payment Type · Payment Impact**")
        issued_range = get_date_range("issued_checks", "payment_date", subsidiary)
        if issued_range:
            st.info(f"Data already uploaded: **{issued_range}**")
        else:
            st.info("No issued checks uploaded yet.")
        issued_file = st.file_uploader("Choose CSV", type="csv", key="up_issued")

        if issued_file:
            try:
                raw = pd.read_csv(issued_file)
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

                    st.info(f"{len(filtered):,} unique checks found ({len(raw) - len(filtered):,} rows aggregated/excluded)")
                    st.dataframe(filtered.head(10), use_container_width=True)

                    if st.button("Add to Issued Checks Database", type="primary", key="btn_issued"):
                        with st.spinner("Saving…"):
                            result = upsert_issued_checks(filtered, subsidiary)
                        st.success(f"{result['inserted']:,} rows added · {result['skipped']:,} duplicates skipped")
            except Exception as exc:
                st.error(f"Could not read file: {exc}")

    # ── Cleared Checks ───────────────────────────────────────────────────
    with col_cleared:
        st.subheader("Cleared Checks (Bank)")
        st.caption("Required columns: **Post Date · Transaction Name - BAI · Customer Reference · Status · Amount**")
        cleared_range = get_date_range("cleared_checks", "date", subsidiary)
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
                    filtered["amount"] = filtered["amount"].abs()

                    st.info(f"{len(filtered):,} check rows found ({len(raw) - len(filtered):,} non-check rows excluded)")
                    st.dataframe(filtered.head(10), use_container_width=True)

                    if st.button("Add to Cleared Checks Database", type="primary", key="btn_cleared"):
                        with st.spinner("Saving…"):
                            result = upsert_cleared_checks(filtered, subsidiary)
                        st.success(f"{result['inserted']:,} rows added · {result['skipped']:,} duplicates skipped")
            except Exception as exc:
                st.error(f"Could not read file: {exc}")


# ════════════════════════════════════════════════════════════════════════════
# PAGE: RECONCILIATION & DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
elif page == "Reconciliation & Dashboard":
    st.title(f"Reconciliation & Dashboard — {subsidiary}")

    with st.spinner("Loading data…"):
        issued = get_issued_checks(subsidiary)
        cleared = get_cleared_checks(subsidiary)
        seed = get_seed_checks(subsidiary)

    if issued.empty and seed.empty:
        st.warning("No check data in the database yet. Go to **Upload Files** or **Seed Upload (Admin)** to get started.")
        st.stop()

    results = reconcile(issued, cleared, seed)
    stats = results["stats"]
    outstanding = results["outstanding"]
    disc = results["discrepancies"]

    # ── KPI row ──────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Seed Checks (Historical)", f"{stats['total_seed']:,}", fmt_acct(stats['seed_amount']))
    k2.metric("Issued Checks", f"{stats['total_issued']:,}", fmt_acct(stats['issued_amount']))
    k3.metric("Cleared Checks", f"{stats['total_cleared']:,}", fmt_acct(stats['cleared_amount']))
    k4.metric("Outstanding Checks", f"{stats['total_outstanding']:,}", fmt_acct(stats['outstanding_amount']))
    k5.metric("Total Discrepancies", f"{stats['amount_mismatches'] + stats['ghost_checks']:,}", delta_color="inverse")

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
        display["Amount"] = display["Amount"].map(fmt_acct)

        st.dataframe(display, use_container_width=True, hide_index=True)

        buf = io.StringIO()
        display.to_csv(buf, index=False)
        st.download_button(
            label="Download Outstanding Checks CSV",
            data=buf.getvalue(),
            file_name=f"outstanding_checks_{subsidiary.replace(' ', '_')}_{pd.Timestamp.today().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="primary",
        )

    st.divider()

    # ── Discrepancy tabs ─────────────────────────────────────────────────
    st.subheader("Discrepancy Dashboard")

    tab1, tab2, tab3 = st.tabs([
        f"Amount Mismatches  ({stats['amount_mismatches']})",
        f"Unrecognized Cleared Checks  ({stats['ghost_checks']})",
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
            display["Amount"] = display["Amount"].map(fmt_acct)
            st.dataframe(display, use_container_width=True, hide_index=True)

    with tab3:
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
            .assign(Amount=lambda d: d["Amount"].map(fmt_acct)),
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

                st.info(
                    f"{len(filtered):,} historical check records found "
                    f"({len(raw) - len(filtered):,} non-check rows excluded)"
                )
                st.dataframe(filtered.head(10), use_container_width=True)

                st.warning("This action cannot be undone through the app. Confirm before proceeding.")
                if st.button("Load Seed Data", type="primary"):
                    with st.spinner("Loading seed data…"):
                        result = load_seed_checks(filtered, subsidiary)
                    st.success(f"{result['inserted']:,} historical checks loaded for {subsidiary}.")
        except Exception as exc:
            st.error(f"Could not read file: {exc}")
