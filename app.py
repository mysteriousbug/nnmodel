"""
Streamlit dashboard for analysis_output.xlsx
Run:  streamlit run app.py
"""
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

OUTPUT = "analysis_output.xlsx"
st.set_page_config(page_title="Product EOS x Problem Tickets", layout="wide")
st.title("Product EOS x Problem Ticket Analysis")

if not Path(OUTPUT).exists():
    st.error(f"{OUTPUT} not found. Run `python analyze.py` first.")
    st.stop()


@st.cache_data
def load():
    xl = pd.ExcelFile(OUTPUT)
    return {s: pd.read_excel(xl, sheet_name=s) for s in xl.sheet_names}


sheets = load()


# ---- KPIs ------------------------------------------------------------------
t2 = sheets["2_total_tickets"].set_index("metric")["value"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total tickets in source",  int(t2.get("total_tickets_in_source", 0)))
c2.metric("Matched to a service",      int(t2.get("tickets_matched_to_service", 0)))
c3.metric("Unmatched",                 int(t2.get("tickets_unmatched", 0)))
c4.metric("Services with tickets",     int(t2.get("unique_services_with_tickets", 0)))

with st.expander("Join diagnostics"):
    st.dataframe(sheets["0_diagnostics"], use_container_width=True)

st.divider()


# ---- Test 1 ----------------------------------------------------------------
st.subheader("1. Aging buckets x CTDR-Output vs TDR")
t1 = sheets["1_aging_x_CTDR_TDR"].copy()
order = ["0-30", "31-60", "61-90", "90+", "Unknown"]
t1["age_bucket"] = pd.Categorical(t1["age_bucket"], categories=order, ordered=True)

left, right = st.columns(2)
with left:
    st.caption("By CTDR-Output")
    pv = (t1.groupby(["age_bucket", "CTDR-Output"], observed=False)["ticket_count"]
            .sum().unstack(fill_value=0).reindex(order).dropna(how="all"))
    fig, ax = plt.subplots(figsize=(6, 3.5))
    pv.plot(kind="bar", ax=ax)
    ax.set_ylabel("Tickets"); ax.set_xlabel("Aging bucket (days)")
    plt.xticks(rotation=0); plt.tight_layout()
    st.pyplot(fig)

with right:
    st.caption("By TDR")
    pv = (t1.groupby(["age_bucket", "TDR"], observed=False)["ticket_count"]
            .sum().unstack(fill_value=0).reindex(order).dropna(how="all"))
    fig, ax = plt.subplots(figsize=(6, 3.5))
    pv.plot(kind="bar", ax=ax)
    ax.set_ylabel("Tickets"); ax.set_xlabel("Aging bucket (days)")
    plt.xticks(rotation=0); plt.tight_layout()
    st.pyplot(fig)

with st.expander("Raw table"):
    st.dataframe(t1, use_container_width=True)

st.divider()


# ---- Test 3 ----------------------------------------------------------------
st.subheader("2. Tickets by impact (2=Significant .. 5=No Impact)")
t3 = sheets["3_by_impact"]
fig, ax = plt.subplots(figsize=(6, 3))
ax.bar(t3["impact"].astype(str), t3["ticket_count"])
ax.set_xlabel("Impact"); ax.set_ylabel("Tickets")
plt.tight_layout()
st.pyplot(fig)
st.dataframe(t3, use_container_width=True)

st.divider()


# ---- Test 4 ----------------------------------------------------------------
st.subheader("3. Monthly average tickets — 6 months pre-EOS vs post-EOS")
t4 = sheets["4_monthly_avg"]
fig, ax = plt.subplots(figsize=(6, 3))
x = range(len(t4))
ax.bar([i - 0.2 for i in x], t4["mean_monthly_rate"],   width=0.4, label="Mean")
ax.bar([i + 0.2 for i in x], t4["median_monthly_rate"], width=0.4, label="Median")
ax.set_xticks(list(x)); ax.set_xticklabels(t4["window"])
ax.set_ylabel("Tickets / month / service")
ax.legend(); plt.tight_layout()
st.pyplot(fig)
st.dataframe(t4, use_container_width=True)

st.divider()


# ---- Test 5 ----------------------------------------------------------------
st.subheader("4. Monthly average by impact")
t5 = sheets["5_monthly_by_impact"]
pv = t5.pivot(index="impact", columns="window", values="mean_monthly_rate")
fig, ax = plt.subplots(figsize=(6, 3.5))
pv.plot(kind="bar", ax=ax)
ax.set_ylabel("Mean monthly rate"); ax.set_xlabel("Impact")
plt.xticks(rotation=0); plt.tight_layout()
st.pyplot(fig)
st.dataframe(t5, use_container_width=True)

st.divider()


# ---- Test 6 ----------------------------------------------------------------
st.subheader("5. Per-service — EOS aging x frequency x severity")
t6 = sheets["6_per_service_eos"].dropna(subset=["days_since_eos"])
post = t6[t6["is_post_eos"] == True]
if len(post):
    fig, ax = plt.subplots(figsize=(7, 4))
    sc = ax.scatter(post["days_since_eos"], post["total_tickets"],
                    c=post["mean_impact"], cmap="RdYlGn", s=40, alpha=0.75)
    ax.set_xlabel("Days since EOS")
    ax.set_ylabel("Total tickets")
    cb = plt.colorbar(sc, ax=ax)
    cb.set_label("Mean impact (lower = more severe)")
    plt.tight_layout()
    st.pyplot(fig)
else:
    st.info("No services are past EOS in this dataset.")

st.dataframe(t6.sort_values("total_tickets", ascending=False),
             use_container_width=True)
