"""Generate realistic test data for the audit scheduler."""

from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

OUT = Path("./inputs")
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Auditor roster — 6 per team (2 SAM, 3 AM, 1 Co-Source) = 18 total
# Names are placeholder personas; replace freely.
# ---------------------------------------------------------------------------

ROSTER = {
    "ICS": [
        ("SAM", "Mo Patel"),
        ("SAM", "Priya Ramesh"),
        ("AM", "Ananya Krishnan"),
        ("AM", "Haidi Wong"),
        ("AM", "Karthik Iyer"),
        ("Co-Source", "Rohit Verma"),
    ],
    "T&A": [
        ("SAM", "Sandra Lim"),
        ("SAM", "Vikram Joshi"),
        ("AM", "Meera Pillai"),
        ("AM", "Tom Adebayo"),
        ("AM", "Liu Wei"),
        ("Co-Source", "Aisha Khan"),
    ],
    "DM": [
        ("SAM", "Deepak Rao"),
        ("SAM", "Elena Schmidt"),
        ("AM", "Nisha Bose"),
        ("AM", "Farah Ahmed"),
        ("AM", "Jin Park"),
        ("Co-Source", "Sam O'Connor"),
    ],
}

# ---------------------------------------------------------------------------
# Leaves — mix of 1-week and 2-week ranges scattered across the year.
# Format must match what _parse_leave_range expects.
# ---------------------------------------------------------------------------

LEAVES = {
    "Mo Patel": "12 Aug-19 Aug, 22 Dec-31 Dec",
    "Priya Ramesh": "3 Feb-7 Feb, 5 Oct-16 Oct",
    "Ananya Krishnan": "15 Jun-26 Jun",
    "Haidi Wong": "20 Apr-24 Apr, 14 Sep-18 Sep",
    "Karthik Iyer": "1 May-3 May",
    "Rohit Verma": "10 Aug-21 Aug",
    "Sandra Lim": "9 Mar-13 Mar, 7 Sep-11 Sep",
    "Vikram Joshi": "1 Jul-15 Jul",
    "Meera Pillai": "20 Jan-24 Jan, 17 Aug-21 Aug",
    "Tom Adebayo": "6 Apr-10 Apr",
    "Liu Wei": "23 Feb-27 Feb, 26 Oct-30 Oct",
    "Aisha Khan": "13 Jul-24 Jul",
    "Deepak Rao": "16 Feb-20 Feb, 2 Nov-6 Nov",
    "Elena Schmidt": "27 Apr-1 May",
    "Nisha Bose": "8 Jun-19 Jun",
    "Farah Ahmed": "9 Feb-13 Feb, 21 Sep-25 Sep",
    "Jin Park": "30 Mar-3 Apr",
    "Sam O'Connor": "3 Aug-14 Aug",
}

# ---------------------------------------------------------------------------
# Skills — chosen to overlap with audit titles below so scoring is non-trivial.
# ---------------------------------------------------------------------------

SKILLS = {
    "Mo Patel": ("Python, Red-Teaming, OWASP, AI/ML Security", "CISA, CISSP"),
    "Priya Ramesh": ("Active Directory, IAM, PAM, Network Security", "CISA, CISM"),
    "Ananya Krishnan": ("Python, Quantum Cryptography, LLM Security, Audit Automation", "CAISP"),
    "Haidi Wong": ("PAM, HashiCorp Vault, Session Recording, SQL", ""),
    "Karthik Iyer": ("Ransomware, Malware Analysis, EDR, Threat Hunting", "GCFA"),
    "Rohit Verma": ("Penetration Testing, OWASP, Burp Suite", "OSCP"),
    "Sandra Lim": ("AWS, Azure, Cloud Security, Network Segmentation", "CCSP, CISA"),
    "Vikram Joshi": ("Firewall, Network, Active Directory, Infrastructure", "CISA"),
    "Meera Pillai": ("AWS, Kubernetes, Terraform, DevSecOps", "AWS-SAA"),
    "Tom Adebayo": ("Patching, Endpoint, SCCM, Vulnerability Management", ""),
    "Liu Wei": ("Database, Oracle, SQL Server, DAM", "OCP"),
    "Aisha Khan": ("Network, Firewall, Segmentation, Routing", "CCNP"),
    "Deepak Rao": ("Data Analytics, Python, SQL, Power BI", "CISA"),
    "Elena Schmidt": ("Machine Learning, MLOps, Databricks, Python", ""),
    "Nisha Bose": ("Data Lineage, Data Quality, ETL, Informatica", ""),
    "Farah Ahmed": ("Python, Pandas, Audit Automation, LLM", ""),
    "Jin Park": ("Reporting, Tableau, Power BI, SQL", ""),
    "Sam O'Connor": ("Data Warehouse, Snowflake, dbt, SQL", ""),
}

# ---------------------------------------------------------------------------
# Planned audits — 12 audits spread across quarters, all three primary teams.
# ---------------------------------------------------------------------------

AUDITS = [
    # (number, title, primary, report_date, analytics, total_days, quarter, lead)
    ("2026-GT-001", "AWS Pooled Audit", "T&A", "26/01/2026", "No", 130, "Q1", "Sandra Lim"),
    ("2026-GT-002", "Active Directory & Identity Hygiene", "ICS", "16/02/2026", "No", 110, "Q1", "Priya Ramesh"),
    ("2026-GT-003", "Data Lineage & Quality Controls", "DM", "23/03/2026", "Yes", 140, "Q1", "Deepak Rao"),
    ("2026-GT-004", "Privileged Access Management (OneVault)", "ICS", "20/04/2026", "Yes", 160, "Q2", "Mo Patel"),
    ("2026-GT-005", "Network Firewall & Segmentation Review", "T&A", "18/05/2026", "No", 120, "Q2", "Vikram Joshi"),
    ("2026-GT-006", "ML Model Risk & MLOps Governance", "DM", "22/06/2026", "Yes", 150, "Q2", "Elena Schmidt"),
    ("2026-GT-007", "Ransomware & Malware Resilience", "ICS", "20/07/2026", "No", 130, "Q3", "Mo Patel"),
    ("2026-GT-008", "Cloud Patching & Vulnerability Management", "T&A", "17/08/2026", "Yes", 120, "Q3", "Sandra Lim"),
    ("2026-GT-009", "Data Warehouse Migration Controls", "DM", "21/09/2026", "No", 110, "Q3", "Deepak Rao"),
    ("2026-GT-010", "Endpoint DLP & Sensitivity Labels", "ICS", "19/10/2026", "Yes", 100, "Q4", "Priya Ramesh"),
    ("2026-GT-011", "Database Activity Monitoring (DAM) Audit", "T&A", "23/11/2026", "Yes", 130, "Q4", "Vikram Joshi"),
    ("2026-GT-012", "AI Factory & LLM Red-Teaming Audit", "ICS", "14/12/2026", "Yes", 140, "Q4", "Mo Patel"),
]

# ---------------------------------------------------------------------------
# Interests — each auditor lists 3 audits they want.
# Crafted so most auditors have at least one that fits their skills.
# ---------------------------------------------------------------------------

INTERESTS = {
    "Mo Patel": ["2026-GT-012", "2026-GT-004", "2026-GT-007"],
    "Priya Ramesh": ["2026-GT-002", "2026-GT-010", "2026-GT-004"],
    "Ananya Krishnan": ["2026-GT-012", "2026-GT-004", "2026-GT-007"],
    "Haidi Wong": ["2026-GT-004", "2026-GT-011", "2026-GT-002"],
    "Karthik Iyer": ["2026-GT-007", "2026-GT-010", "2026-GT-012"],
    "Rohit Verma": ["2026-GT-012", "2026-GT-007", "2026-GT-010"],
    "Sandra Lim": ["2026-GT-001", "2026-GT-008", "2026-GT-005"],
    "Vikram Joshi": ["2026-GT-005", "2026-GT-002", "2026-GT-011"],
    "Meera Pillai": ["2026-GT-001", "2026-GT-008", "2026-GT-006"],
    "Tom Adebayo": ["2026-GT-008", "2026-GT-005", "2026-GT-010"],
    "Liu Wei": ["2026-GT-011", "2026-GT-009", "2026-GT-003"],
    "Aisha Khan": ["2026-GT-005", "2026-GT-001", "2026-GT-008"],
    "Deepak Rao": ["2026-GT-003", "2026-GT-009", "2026-GT-006"],
    "Elena Schmidt": ["2026-GT-006", "2026-GT-012", "2026-GT-003"],
    "Nisha Bose": ["2026-GT-003", "2026-GT-009", "2026-GT-011"],
    "Farah Ahmed": ["2026-GT-003", "2026-GT-006", "2026-GT-012"],
    "Jin Park": ["2026-GT-009", "2026-GT-003", "2026-GT-011"],
    "Sam O'Connor": ["2026-GT-009", "2026-GT-003", "2026-GT-006"],
}

# ---------------------------------------------------------------------------
# Prior assignments (planned_assignments.xlsx) — sparse, just enough so the
# prior-domain scorer has something to chew on.
# Each entry: (auditor, [(week_label, audit_title), ...])
# ---------------------------------------------------------------------------

# Build a list of 52 weekly labels matching the format the scheduler expects.
WEEK_LABELS = []  # filled below from WEEK_DATES
import datetime as _dt
_first = _dt.date(2026, 1, 5)  # first Monday of 2026
WEEK_DATES = [_first + _dt.timedelta(weeks=i) for i in range(52)]
WEEK_LABELS = [f"{d.day}/{d.strftime('%b')}" for d in WEEK_DATES]
MONTH_LABELS = []
for d in WEEK_DATES:
    m = d.strftime("%b-%y")
    MONTH_LABELS.append(m if (not MONTH_LABELS or MONTH_LABELS[-1] != m) else "")

# Map: auditor -> {week_label: audit_title}
# We'll seed prior data spanning 2025 patterns, recorded under 2026 week columns
# as a stand-in (the scheduler only reads title strings, not dates, from this file).
PRIOR = {
    "Sandra Lim": {
        "5/Jan": "AWS Pooled Audit 2025", "12/Jan": "AWS Pooled Audit 2025",
        "19/Jan": "AWS Pooled Audit 2025",
    },
    "Priya Ramesh": {
        "2/Feb": "Active Directory Review 2025", "9/Feb": "Active Directory Review 2025",
        "16/Feb": "Active Directory Review 2025",
    },
    "Mo Patel": {
        "6/Apr": "PAM Audit 2025", "13/Apr": "PAM Audit 2025", "20/Apr": "PAM Audit 2025",
        "5/Oct": "AI Factory Red-Teaming 2025", "12/Oct": "AI Factory Red-Teaming 2025",
    },
    "Vikram Joshi": {
        "4/May": "Network Segmentation 2025", "11/May": "Network Segmentation 2025",
    },
    "Deepak Rao": {
        "9/Mar": "Data Quality Controls 2025", "16/Mar": "Data Quality Controls 2025",
        "23/Mar": "Data Quality Controls 2025",
    },
    "Elena Schmidt": {
        "8/Jun": "ML Governance Pilot 2025", "15/Jun": "ML Governance Pilot 2025",
    },
    "Karthik Iyer": {
        "13/Jul": "Ransomware Resilience 2025", "20/Jul": "Ransomware Resilience 2025",
    },
    "Haidi Wong": {
        "7/Sep": "PAM Vault Migration 2025", "14/Sep": "PAM Vault Migration 2025",
    },
    "Liu Wei": {
        "9/Nov": "Database Audit 2025", "16/Nov": "Database Audit 2025",
    },
    "Nisha Bose": {
        "12/Oct": "Data Warehouse Pilot 2025", "19/Oct": "Data Warehouse Pilot 2025",
    },
    "Ananya Krishnan": {
        "5/Oct": "AI Factory Red-Teaming 2025", "12/Oct": "AI Factory Red-Teaming 2025",
    },
}


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _header(ws, headers):
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="305496")


def write_leave_tracker():
    wb = Workbook()
    wb.remove(wb.active)
    for team, members in ROSTER.items():
        ws = wb.create_sheet(team)
        _header(ws, ["Auditor", "Planned_Leaves"])
        for role, name in members:
            ws.append([f"{role}/{name}", LEAVES.get(name, "")])
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 40
    wb.save(OUT / "leave_tracker.xlsx")


def write_skills():
    wb = Workbook()
    wb.remove(wb.active)
    for team, members in ROSTER.items():
        ws = wb.create_sheet(team)
        _header(ws, ["Auditor", "Skills", "Certifications"])
        for role, name in members:
            skills, certs = SKILLS.get(name, ("", ""))
            ws.append([f"{role}/{name}", skills, certs])
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["C"].width = 25
    wb.save(OUT / "skills.xlsx")


def write_planned_audits():
    wb = Workbook()
    wb.remove(wb.active)
    headers = ["Audit Number", "TITLE", "Audit Primary Team", "REPORT ISSUANCE PLANNED",
               "Analytics Used", "Total Auditor Days", "Reporting Quarter", "Team Lead"]
    # Same audit list goes into every team sheet — the scheduler deduplicates by number.
    for team in ROSTER:
        ws = wb.create_sheet(team)
        _header(ws, headers)
        for row in AUDITS:
            ws.append(list(row))
        for col_letter, w in zip("ABCDEFGH", [16, 45, 18, 22, 16, 18, 18, 20]):
            ws.column_dimensions[col_letter].width = w
    wb.save(OUT / "planned_audits.xlsx")


def write_interests():
    wb = Workbook()
    wb.remove(wb.active)
    for team, members in ROSTER.items():
        ws = wb.create_sheet(team)
        _header(ws, ["Auditor", "Audit_Preference1", "Audit_Preference2", "Audit_Preference3"])
        for role, name in members:
            prefs = INTERESTS.get(name, ["", "", ""])
            ws.append([f"{role}/{name}"] + prefs)
        ws.column_dimensions["A"].width = 30
        for col_letter in "BCD":
            ws.column_dimensions[col_letter].width = 18
    wb.save(OUT / "interests.xlsx")


def write_planned_assignments():
    wb = Workbook()
    wb.remove(wb.active)
    for team, members in ROSTER.items():
        ws = wb.create_sheet(team)
        # Row 1: month labels (col A blank, then months above each week)
        ws.cell(row=1, column=1, value="")
        for i, m in enumerate(MONTH_LABELS, start=2):
            c = ws.cell(row=1, column=i, value=m)
            if m:
                c.font = Font(bold=True)
        # Row 2: "Auditor" + week labels
        ws.cell(row=2, column=1, value="Auditor").font = Font(bold=True)
        for i, wk in enumerate(WEEK_LABELS, start=2):
            ws.cell(row=2, column=i, value=wk).font = Font(bold=True)
        # Data rows
        for r, (role, name) in enumerate(members, start=3):
            ws.cell(row=r, column=1, value=f"{role}/{name}")
            row_prior = PRIOR.get(name, {})
            for i, wk in enumerate(WEEK_LABELS, start=2):
                if wk in row_prior:
                    ws.cell(row=r, column=i, value=row_prior[wk])
        ws.column_dimensions["A"].width = 28
        for i in range(2, len(WEEK_LABELS) + 2):
            from openpyxl.utils import get_column_letter
            ws.column_dimensions[get_column_letter(i)].width = 14
        ws.freeze_panes = "B3"
    wb.save(OUT / "planned_assignments.xlsx")


def main():
    write_leave_tracker()
    write_skills()
    write_planned_audits()
    write_interests()
    write_planned_assignments()
    print("Generated test files in", OUT.resolve())
    for f in sorted(OUT.iterdir()):
        print(" -", f.name)


if __name__ == "__main__":
    main()
