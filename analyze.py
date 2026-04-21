"""
Product List x Problem Tickets - Analysis
==========================================
Matched to refined schemas.

Product list columns used:
    Application Service, Product EOS Date Status, Is In CTDR-Output,
    Is In TDR, Product Name

Problem tickets columns used:
    number, sys_created_on, closed_at, cmdb_ci, priority, impact

Run:
    pip install pandas numpy openpyxl
    python analyze.py
"""

from __future__ import annotations
import re
from datetime import datetime
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PRODUCT_FILE = "product_list_input.xlsx"
TICKETS_FILE = "problem_tickets.xlsx"
OUTPUT_FILE  = "analysis_output.xlsx"
TODAY        = pd.Timestamp(datetime.now().date())

PRODUCT_COLS = [
    "Application Service",
    "Product EOS Date Status",
    "Is In CTDR-Output",
    "Is In TDR",
    "Product Name",
]
TICKET_COLS = [
    "number",
    "sys_created_on",
    "closed_at",
    "cmdb_ci",
    "priority",
    "impact",
]

AGING_BUCKETS = [(0, 30, "0-30"), (31, 60, "31-60"),
                 (61, 90, "61-90"), (91, np.inf, "90+")]

IMPACT_LEVELS = [2, 3, 4, 5]   # actual values present in this dataset


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------
def parse_dmy(val):
    """Parse product EOS date: dd/mm/yyyy (sometimes with single-digit day/month)."""
    if pd.isna(val):
        return pd.NaT
    if isinstance(val, (pd.Timestamp, datetime)):
        # Excel may already have given us a real datetime - trust it.
        return pd.Timestamp(val)
    s = str(val).strip()
    if not s:
        return pd.NaT
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


# Matches e.g. "15-07-2024 06:28:20" (dd-mm-yyyy) vs "12/6/2024 10:37:11 PM" (mm/dd/yyyy)
_DASH_DMY = re.compile(r"^\s*\d{1,2}-\d{1,2}-\d{4}")


def parse_ticket_ts(val):
    """Parse ticket timestamps with mixed formats:
       - 'dd-mm-yyyy HH:MM:SS'            (dash-separated -> dayfirst)
       - 'mm/dd/yyyy HH:MM:SS AM/PM'      (slash-separated -> monthfirst)
    """
    if pd.isna(val):
        return pd.NaT
    if isinstance(val, (pd.Timestamp, datetime)):
        return pd.Timestamp(val)
    s = str(val).strip()
    if not s:
        return pd.NaT
    dayfirst = bool(_DASH_DMY.match(s))
    return pd.to_datetime(s, dayfirst=dayfirst, errors="coerce")


def parse_impact(val):
    """Impact arrives as '5 - No Impact / Single User' etc. Extract the leading int."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    m = re.match(r"\s*(\d+)", s)
    return int(m.group(1)) if m else np.nan


def yn(val):
    """Yes or blank -> Yes / No."""
    if pd.isna(val):
        return "No"
    return "Yes" if str(val).strip().lower() == "yes" else "No"


def bucket_age(days):
    if pd.isna(days) or days < 0:
        return "Unknown"
    for lo, hi, label in AGING_BUCKETS:
        if lo <= days <= hi:
            return label
    return "Unknown"


def safe_read_excel(path, wanted):
    header = pd.read_excel(path, nrows=0)
    present = [c for c in wanted if c in header.columns]
    missing = [c for c in wanted if c not in header.columns]
    if missing:
        print(f"  [WARN] Missing in {path}: {missing}")
    return pd.read_excel(path, usecols=present)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
print("Loading files...")
products = safe_read_excel(PRODUCT_FILE, PRODUCT_COLS)
tickets  = safe_read_excel(TICKETS_FILE, TICKET_COLS)
print(f"  products: {products.shape}")
print(f"  tickets:  {tickets.shape}")

# --- Product transforms ---
products["eos_date"] = products["Product EOS Date Status"].apply(parse_dmy)
products["_ctdr"]    = products["Is In CTDR-Output"].apply(yn)
products["_tdr"]     = products["Is In TDR"].apply(yn)
products["_key"]     = (products["Application Service"].astype(str)
                        .str.strip().str.casefold())

n_bad_eos = products["eos_date"].isna().sum() - products["Product EOS Date Status"].isna().sum()
if n_bad_eos > 0:
    print(f"  [WARN] {n_bad_eos} product rows had unparseable EOS dates.")

# --- Ticket transforms ---
tickets["created"] = tickets["sys_created_on"].apply(parse_ticket_ts)
tickets["closed"]  = tickets["closed_at"].apply(parse_ticket_ts)
tickets["impact_int"] = tickets["impact"].apply(parse_impact)
tickets["_key"]    = (tickets["cmdb_ci"].astype(str)
                      .str.strip().str.casefold())

n_bad_created = tickets["created"].isna().sum() - tickets["sys_created_on"].isna().sum()
if n_bad_created > 0:
    print(f"  [WARN] {n_bad_created} ticket rows had unparseable sys_created_on.")


# ---------------------------------------------------------------------------
# Aggregate products per service (prevents fan-out).
# If multiple products share a service, we use the EARLIEST EOS as the
# service's EOS - conservative choice: the service is "exposed" from the
# moment any of its products goes EOS.
# ---------------------------------------------------------------------------
print("Aggregating products per Application Service...")
svc = (products.groupby("_key", as_index=False)
       .agg(application_service=("Application Service", "first"),
            earliest_eos=("eos_date", "min"),
            latest_eos  =("eos_date", "max"),
            product_rows=("_key", "size"),
            any_ctdr=("_ctdr", lambda s: "Yes" if (s == "Yes").any() else "No"),
            any_tdr =("_tdr",  lambda s: "Yes" if (s == "Yes").any() else "No"),
            product_name_sample=("Product Name", "first")))
print(f"  unique services: {len(svc)}")


# ---------------------------------------------------------------------------
# Join tickets -> services
# ---------------------------------------------------------------------------
print("Joining tickets to services...")
jt = tickets.merge(svc, on="_key", how="left")
jt["has_product_match"] = jt["product_rows"].notna()
jt["age_days"]   = (TODAY - jt["created"]).dt.days
jt["age_bucket"] = jt["age_days"].apply(bucket_age)
print(f"  ticket rows: {len(jt)}  "
      f"(matched: {int(jt['has_product_match'].sum())}, "
      f"unmatched: {int((~jt['has_product_match']).sum())})")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------
diag = pd.DataFrame({
    "metric": [
        "product_rows_loaded",
        "unique_application_services",
        "services_with_eos_date",
        "ticket_rows_loaded",
        "tickets_with_valid_created_date",
        "tickets_matching_a_service",
        "tickets_unmatched",
        "max_product_rows_behind_one_service",
        "mean_product_rows_per_service",
    ],
    "value": [
        len(products),
        len(svc),
        int(svc["earliest_eos"].notna().sum()),
        len(tickets),
        int(tickets["created"].notna().sum()),
        int(jt["has_product_match"].sum()),
        int((~jt["has_product_match"]).sum()),
        int(svc["product_rows"].max()) if len(svc) else 0,
        float(svc["product_rows"].mean()) if len(svc) else 0.0,
    ],
})
print("\nDiagnostics:")
print(diag.to_string(index=False))


# ---------------------------------------------------------------------------
# Test 1 - Aging x CTDR-Output vs TDR (matched tickets only)
# ---------------------------------------------------------------------------
matched = jt[jt["has_product_match"]].copy()
order = ["0-30", "31-60", "61-90", "90+", "Unknown"]
matched["age_bucket"] = pd.Categorical(matched["age_bucket"],
                                        categories=order, ordered=True)

test1 = (matched.groupby(["age_bucket", "any_ctdr", "any_tdr"],
                          observed=False)
         .size().reset_index(name="ticket_count")
         .rename(columns={"any_ctdr": "CTDR-Output", "any_tdr": "TDR"}))


# ---------------------------------------------------------------------------
# Test 2 - Totals
# ---------------------------------------------------------------------------
test2 = pd.DataFrame({
    "metric": ["total_tickets_in_source",
               "tickets_matched_to_service",
               "tickets_unmatched",
               "unique_services_with_tickets"],
    "value": [len(tickets),
              int(jt["has_product_match"].sum()),
              int((~jt["has_product_match"]).sum()),
              int(matched["_key"].nunique())],
})


# ---------------------------------------------------------------------------
# Test 3 - By impact level (2..5)
# ---------------------------------------------------------------------------
impact_counts = (matched["impact_int"]
                 .value_counts()
                 .reindex(IMPACT_LEVELS, fill_value=0))
test3 = pd.DataFrame({"impact": IMPACT_LEVELS,
                      "ticket_count": impact_counts.values})


# ---------------------------------------------------------------------------
# Tests 4 & 5 - Monthly averages pre/post EOS
# Per service: window bounded by today so future EOS dates don't get
# credited months they haven't lived.
# ---------------------------------------------------------------------------
def pre_eos_window(eos):
    if pd.isna(eos):
        return None, None, 0.0
    start = eos - pd.DateOffset(months=6)
    end   = min(eos, TODAY)
    if end <= start:
        return start, end, 0.0
    return start, end, (end - start).days / 30.4375


def post_eos_window(eos):
    if pd.isna(eos) or eos >= TODAY:
        return None, None, 0.0
    return eos, TODAY, (TODAY - eos).days / 30.4375


def rates(window_fn, impact_filter=None):
    rows = []
    by_svc = {k: g for k, g in matched.groupby("_key")}
    for _, row in svc.iterrows():
        start, end, months = window_fn(row["earliest_eos"])
        if months <= 0:
            continue
        g = by_svc.get(row["_key"])
        if g is None or g.empty:
            tk = 0
        else:
            mask = g["created"].between(start, end)
            if impact_filter is not None:
                mask &= (g["impact_int"] == impact_filter)
            tk = int(mask.sum())
        rows.append({
            "application_service": row["application_service"],
            "eos_date": row["earliest_eos"],
            "window_start": start,
            "window_end": end,
            "months_observed": round(months, 2),
            "tickets": tk,
            "monthly_rate": tk / months,
        })
    return pd.DataFrame(rows)


print("Computing pre/post EOS monthly rates...")
pre_all  = rates(pre_eos_window)
post_all = rates(post_eos_window)


def summarise(df, label):
    if df.empty:
        return {"window": label, "services_with_window": 0,
                "mean_monthly_rate": 0, "median_monthly_rate": 0,
                "total_tickets_in_window": 0}
    return {"window": label,
            "services_with_window": len(df),
            "mean_monthly_rate":   df["monthly_rate"].mean(),
            "median_monthly_rate": df["monthly_rate"].median(),
            "total_tickets_in_window": int(df["tickets"].sum())}


test4 = pd.DataFrame([summarise(pre_all,  "6 months BEFORE EOS"),
                      summarise(post_all, "AFTER EOS")])

rows5 = []
for label, fn in [("pre_EOS_6mo", pre_eos_window),
                  ("post_EOS",    post_eos_window)]:
    for i in IMPACT_LEVELS:
        df = rates(fn, impact_filter=i)
        rows5.append({
            "window": label, "impact": i,
            "services_with_window": len(df),
            "mean_monthly_rate":   df["monthly_rate"].mean()   if len(df) else 0,
            "median_monthly_rate": df["monthly_rate"].median() if len(df) else 0,
            "total_tickets": int(df["tickets"].sum())           if len(df) else 0,
        })
test5 = pd.DataFrame(rows5)


# ---------------------------------------------------------------------------
# Test 6 - Per-service EOS aging x frequency x severity
# Severity proxy = mean impact (lower = more severe in ServiceNow).
# ---------------------------------------------------------------------------
per_rows = []
by_svc = {k: g for k, g in matched.groupby("_key")}
for _, row in svc.iterrows():
    g = by_svc.get(row["_key"], pd.DataFrame())
    eos = row["earliest_eos"]
    per_rows.append({
        "application_service": row["application_service"],
        "product_name_sample": row["product_name_sample"],
        "eos_date": eos,
        "days_since_eos": (TODAY - eos).days if pd.notna(eos) else np.nan,
        "is_post_eos": bool(pd.notna(eos) and eos < TODAY),
        "total_tickets": len(g),
        "impact_2": int((g["impact_int"] == 2).sum()) if len(g) else 0,
        "impact_3": int((g["impact_int"] == 3).sum()) if len(g) else 0,
        "impact_4": int((g["impact_int"] == 4).sum()) if len(g) else 0,
        "impact_5": int((g["impact_int"] == 5).sum()) if len(g) else 0,
        "mean_impact": g["impact_int"].mean() if len(g) else np.nan,
    })
test6 = pd.DataFrame(per_rows).sort_values("total_tickets", ascending=False)


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------
print(f"Writing {OUTPUT_FILE}...")
with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as xw:
    diag.to_excel(xw,  sheet_name="0_diagnostics",       index=False)
    test1.to_excel(xw, sheet_name="1_aging_x_CTDR_TDR",  index=False)
    test2.to_excel(xw, sheet_name="2_total_tickets",     index=False)
    test3.to_excel(xw, sheet_name="3_by_impact",         index=False)
    test4.to_excel(xw, sheet_name="4_monthly_avg",       index=False)
    test5.to_excel(xw, sheet_name="5_monthly_by_impact", index=False)
    test6.to_excel(xw, sheet_name="6_per_service_eos",   index=False)
    pre_all.to_excel(xw,  sheet_name="detail_pre_EOS_rates",  index=False)
    post_all.to_excel(xw, sheet_name="detail_post_EOS_rates", index=False)
    (jt.drop(columns=["_key"])
       .to_excel(xw, sheet_name="joined_tickets", index=False))

print("\nDone.")
print(f"  Output: {OUTPUT_FILE}")
print("Run the dashboard with:  streamlit run app.py")
