"""
Product List x Problem Tickets — Join & Analysis
=================================================
Join:  product_list.Application Service  ==  problem_tickets.Configuration Item
Output: analysis_output.xlsx  (multi-sheet)

Run:
    pip install pandas numpy openpyxl python-dateutil
    python analyze.py
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PRODUCT_FILE  = "product_list_input.xlsx"
TICKETS_FILE  = "problem_tickets.xlsx"
OUTPUT_FILE   = "analysis_output.xlsx"
TODAY         = pd.Timestamp(datetime.now().date())

AGING_BUCKETS = [(0, 30, "0-30"), (31, 60, "31-60"),
                 (61, 90, "61-90"), (91, np.inf, "90+")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_col(df: pd.DataFrame, *candidates: str) -> str | None:
    """Return the first column in df whose name matches any candidate
    (case/whitespace/underscore-insensitive). None if nothing matches."""
    norm = {c.lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for cand in candidates:
        key = cand.lower().replace(" ", "").replace("_", "")
        if key in norm:
            return norm[key]
    return None


def require(col: str | None, label: str, df_name: str) -> str:
    if col is None:
        sys.exit(f"[FATAL] Could not find '{label}' column in {df_name}. "
                 f"Columns present: {list(col for col in [])}")
    return col


def bucket_age(days: float) -> str:
    if pd.isna(days) or days < 0:
        return "Unknown"
    for lo, hi, label in AGING_BUCKETS:
        if lo <= days <= hi:
            return label
    return "Unknown"


def months_between(a: pd.Timestamp, b: pd.Timestamp) -> float:
    """Signed month count between two timestamps (b - a)."""
    if pd.isna(a) or pd.isna(b):
        return np.nan
    return (b - a).days / 30.4375


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
print("Loading files...")
products = pd.read_excel(PRODUCT_FILE)
tickets  = pd.read_excel(TICKETS_FILE)
print(f"  products: {products.shape}")
print(f"  tickets:  {tickets.shape}")

# Column resolution ----------------------------------------------------------
p_app_svc  = find_col(products, "Application Service")
p_eos      = find_col(products, "Product EOES Date", "Product EOS Date",
                      "Product EOS")
p_ctdr_out = find_col(products, "Is In CTDR-Output", "Is In CTDR Output")
p_tdr      = find_col(products, "Is In TDR")
p_name     = find_col(products, "Name With Serial Number", "Name")

t_ci       = find_col(tickets, "Configuration Item", "cmdb_ci",
                      "u_configuration_item", "business_service")
t_start    = find_col(tickets, "work_start", "sys_created_on", "opened_at")
t_impact   = find_col(tickets, "impact")
t_number   = find_col(tickets, "number")

for col, label, dfname in [
    (p_app_svc,  "Application Service", "product_list"),
    (p_eos,      "Product EOS/EOES Date", "product_list"),
    (t_ci,       "Configuration Item", "problem_tickets"),
    (t_start,    "work_start", "problem_tickets"),
    (t_impact,   "impact", "problem_tickets"),
    (t_number,   "number", "problem_tickets"),
]:
    if col is None:
        print(f"[WARN] '{label}' not found in {dfname}")

# Type coercion --------------------------------------------------------------
products[p_eos]  = pd.to_datetime(products[p_eos], errors="coerce")
tickets[t_start] = pd.to_datetime(tickets[t_start], errors="coerce")
tickets[t_impact] = pd.to_numeric(tickets[t_impact], errors="coerce")

# Normalise join keys (strip/casefold to reduce false mismatches) ------------
products["_join_key"] = (products[p_app_svc].astype(str)
                         .str.strip().str.casefold())
tickets["_join_key"]  = (tickets[t_ci].astype(str)
                         .str.strip().str.casefold())

# ---------------------------------------------------------------------------
# Join  (left: product → tickets)
# ---------------------------------------------------------------------------
print("Joining...")
joined = products.merge(tickets, on="_join_key", how="left",
                        suffixes=("_prod", "_tkt"))
print(f"  joined rows: {len(joined)}")

# Derive helpers on joined frame --------------------------------------------
joined["age_days"]  = (TODAY - joined[t_start]).dt.days
joined["age_bucket"] = joined["age_days"].apply(bucket_age)
joined["months_from_eos"] = joined.apply(
    lambda r: months_between(r[p_eos], r[t_start]), axis=1)
# negative => ticket before EOS, positive => after EOS


# ---------------------------------------------------------------------------
# Test 1 — Aging buckets × CTDR-Output vs TDR
# ---------------------------------------------------------------------------
def yn(val) -> str:
    """Normalise flags (True/'Yes'/1 → 'Yes') for pivoting."""
    if pd.isna(val):
        return "No"
    s = str(val).strip().lower()
    return "Yes" if s in {"yes", "true", "1", "y"} else "No"


has_ticket = joined[t_number].notna()
t1_src = joined[has_ticket].copy()
t1_src["CTDR-Output"] = t1_src[p_ctdr_out].apply(yn) if p_ctdr_out else "Unknown"
t1_src["TDR"]         = t1_src[p_tdr].apply(yn)     if p_tdr     else "Unknown"

test1 = (t1_src.groupby(["age_bucket", "CTDR-Output", "TDR"])
         .size().reset_index(name="ticket_count"))


# ---------------------------------------------------------------------------
# Test 2 — Total tickets  (unique ticket numbers)
# ---------------------------------------------------------------------------
test2 = pd.DataFrame({
    "metric": ["total_tickets_joined_rows",
               "total_unique_tickets_in_source",
               "unique_tickets_matching_a_product"],
    "value":  [int(has_ticket.sum()),
               int(tickets[t_number].nunique()),
               int(joined.loc[has_ticket, t_number].nunique())],
})


# ---------------------------------------------------------------------------
# Test 3 — Tickets by impact 1..4
# ---------------------------------------------------------------------------
imp_src = joined[has_ticket].copy()
imp_src["impact_clean"] = imp_src[t_impact].where(
    imp_src[t_impact].isin([1, 2, 3, 4]), other=np.nan)
test3 = (imp_src.dropna(subset=["impact_clean"])
         .groupby("impact_clean").size()
         .reindex([1, 2, 3, 4], fill_value=0)
         .reset_index(name="ticket_count")
         .rename(columns={"impact_clean": "impact"}))


# ---------------------------------------------------------------------------
# Test 4 & 5 — Monthly avg tickets in 6 months BEFORE EOS (overall + by impact)
#
# Methodology: for each product, exposure window in the pre-EOS 6-month band
# is capped by today (if EOS is in the future we haven't observed all 6 mo yet).
# Monthly rate per product = tickets_in_window / months_observed.
# Report cross-product mean of that rate.
# ---------------------------------------------------------------------------
def pre_eos_window(eos: pd.Timestamp):
    """Return (start, end, months_observed) for the 6-mo pre-EOS window,
    capped so we never count future time."""
    if pd.isna(eos):
        return None, None, 0.0
    start = eos - pd.DateOffset(months=6)
    end   = min(eos, TODAY)
    if end <= start:
        return start, end, 0.0
    return start, end, (end - start).days / 30.4375


def post_eos_window(eos: pd.Timestamp):
    """EOS → today."""
    if pd.isna(eos) or eos >= TODAY:
        return None, None, 0.0
    return eos, TODAY, (TODAY - eos).days / 30.4375


def monthly_rates(window_fn, impact_filter=None) -> pd.DataFrame:
    """For each product compute tickets-in-window / months_observed."""
    rows = []
    grp = joined.groupby([p_app_svc, p_eos], dropna=False)
    for (svc, eos), g in grp:
        start, end, months = window_fn(eos)
        if months <= 0:
            continue
        g_tickets = g[g[t_number].notna() & g[t_start].between(start, end)]
        if impact_filter is not None:
            g_tickets = g_tickets[g_tickets[t_impact] == impact_filter]
        rows.append({
            p_app_svc: svc,
            "eos_date": eos,
            "window_start": start,
            "window_end": end,
            "months_observed": round(months, 2),
            "tickets": len(g_tickets),
            "monthly_rate": len(g_tickets) / months,
        })
    return pd.DataFrame(rows)


pre_all  = monthly_rates(pre_eos_window)
post_all = monthly_rates(post_eos_window)

test4 = pd.DataFrame({
    "window": ["6 months BEFORE EOS", "AFTER EOS"],
    "products_with_window": [len(pre_all), len(post_all)],
    "mean_monthly_rate":    [pre_all["monthly_rate"].mean() if len(pre_all) else 0,
                              post_all["monthly_rate"].mean() if len(post_all) else 0],
    "median_monthly_rate":  [pre_all["monthly_rate"].median() if len(pre_all) else 0,
                              post_all["monthly_rate"].median() if len(post_all) else 0],
    "total_tickets_in_window": [pre_all["tickets"].sum() if len(pre_all) else 0,
                                 post_all["tickets"].sum() if len(post_all) else 0],
})

# Test 5 — same but broken out by impact 1..4
impact_rows = []
for window_label, window_fn in [("pre_EOS_6mo", pre_eos_window),
                                ("post_EOS",    post_eos_window)]:
    for imp in [1, 2, 3, 4]:
        df = monthly_rates(window_fn, impact_filter=imp)
        impact_rows.append({
            "window": window_label,
            "impact": imp,
            "products_with_window": len(df),
            "mean_monthly_rate":   df["monthly_rate"].mean()   if len(df) else 0,
            "median_monthly_rate": df["monthly_rate"].median() if len(df) else 0,
            "total_tickets": int(df["tickets"].sum())           if len(df) else 0,
        })
test5 = pd.DataFrame(impact_rows)


# ---------------------------------------------------------------------------
# Test 6 — Per-product EOS aging × frequency × severity
# Severity proxy: mean impact (lower = more severe in ServiceNow).
# ---------------------------------------------------------------------------
per_prod_rows = []
for (svc, eos), g in joined.groupby([p_app_svc, p_eos], dropna=False):
    g_t = g[g[t_number].notna()]
    eos_age_days = (TODAY - eos).days if pd.notna(eos) else np.nan
    per_prod_rows.append({
        p_app_svc: svc,
        "eos_date": eos,
        "days_since_eos": eos_age_days,
        "is_post_eos": bool(pd.notna(eos) and eos < TODAY),
        "total_tickets": len(g_t),
        "impact_1": int((g_t[t_impact] == 1).sum()),
        "impact_2": int((g_t[t_impact] == 2).sum()),
        "impact_3": int((g_t[t_impact] == 3).sum()),
        "impact_4": int((g_t[t_impact] == 4).sum()),
        "mean_impact": g_t[t_impact].mean() if len(g_t) else np.nan,
    })
test6 = pd.DataFrame(per_prod_rows)


# ---------------------------------------------------------------------------
# Diagnostics — join cardinality (helps spot runaway fan-out)
# ---------------------------------------------------------------------------
match_per_product = (joined.groupby("_join_key")[t_number]
                     .apply(lambda s: s.notna().sum()))
diag = pd.DataFrame({
    "metric": [
        "product_rows",
        "ticket_rows",
        "joined_rows",
        "products_with_at_least_1_ticket_match",
        "products_with_0_ticket_matches",
        "max_tickets_matched_to_one_product",
        "mean_tickets_per_matched_product",
    ],
    "value": [
        len(products),
        len(tickets),
        len(joined),
        int((match_per_product > 0).sum()),
        int((match_per_product == 0).sum()),
        int(match_per_product.max()) if len(match_per_product) else 0,
        float(match_per_product[match_per_product > 0].mean())
            if (match_per_product > 0).any() else 0.0,
    ],
})
print("\nJoin diagnostics:")
print(diag.to_string(index=False))

# ---------------------------------------------------------------------------
# Write output
#
# The joined frame exceeds Excel's 1,048,576-row limit, so:
#   - full joined data -> CSV (unbounded)
#   - Excel workbook -> all aggregate tests + a capped preview of joined data
# ---------------------------------------------------------------------------
joined_export = joined.drop(columns=["_join_key"])
JOINED_CSV = OUTPUT_FILE.replace(".xlsx", "_joined_full.csv")

print(f"\nWriting full joined data -> {JOINED_CSV} ({len(joined_export):,} rows)...")
joined_export.to_csv(JOINED_CSV, index=False)

EXCEL_ROW_LIMIT = 1_048_575  # minus header row
preview = joined_export.head(EXCEL_ROW_LIMIT)

print(f"Writing {OUTPUT_FILE}...")
with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as xw:
    # Aggregate results first (these are what you actually analyse)
    diag.to_excel(xw,  sheet_name="0_join_diagnostics", index=False)
    test1.to_excel(xw, sheet_name="1_aging_x_CTDR_TDR", index=False)
    test2.to_excel(xw, sheet_name="2_total_tickets",    index=False)
    test3.to_excel(xw, sheet_name="3_by_impact",        index=False)
    test4.to_excel(xw, sheet_name="4_monthly_avg",      index=False)
    test5.to_excel(xw, sheet_name="5_monthly_by_impact", index=False)
    test6.to_excel(xw, sheet_name="6_per_product_eos",  index=False)

    # Per-product rate detail
    pre_all.to_excel(xw,  sheet_name="detail_pre_EOS_rates",  index=False)
    post_all.to_excel(xw, sheet_name="detail_post_EOS_rates", index=False)

    # Joined-data preview last (capped at Excel's row limit)
    preview.to_excel(xw, sheet_name="joined_data_preview", index=False)
    if len(joined_export) > len(preview):
        pd.DataFrame({"note": [
            f"joined_data_preview shows the first {len(preview):,} rows.",
            f"Full {len(joined_export):,} rows are in {JOINED_CSV}.",
        ]}).to_excel(xw, sheet_name="_README", index=False)

print("\nDone.")
print(f"  Excel:       {OUTPUT_FILE}")
print(f"  Full joined: {JOINED_CSV}")
print("Run the dashboard with:  streamlit run app.py")
