"""Generate v2 test data for the audit scheduler.

Produces 5 files matching the v2 formats:
  - leave_tracker.xlsx       calendar with daily leave codes
  - skills.xlsx              3 sheets
  - planned_audits.xlsx      SINGLE sheet
  - h1_allocations.xlsx      calendar grid (3 sheets) showing H1 bookings
  - interests.xlsx           SINGLE sheet, audit-row layout
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = Path("./inputs")

YEAR = 2026

# ----------------------------------------------------------------------------
# Roster
# ----------------------------------------------------------------------------

ROSTER = {
    "ICS": [
        ("SAM", "Mo Patel"), ("SAM", "Priya Ramesh"),
        ("AM", "Ananya Krishnan"), ("AM", "Haidi Wong"), ("AM", "Karthik Iyer"),
        ("Co-Source", "Rohit Verma"),
    ],
    "T&A": [
        ("SAM", "Sandra Lim"), ("SAM", "Vikram Joshi"),
        ("AM", "Meera Pillai"), ("AM", "Tom Adebayo"), ("AM", "Liu Wei"),
        ("Co-Source", "Aisha Khan"),
    ],
    "DM": [
        ("SAM", "Deepak Rao"), ("SAM", "Elena Schmidt"),
        ("AM", "Nisha Bose"), ("AM", "Farah Ahmed"), ("AM", "Jin Park"),
        ("Co-Source", "Sam O'Connor"),
    ],
}

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

# ----------------------------------------------------------------------------
# Calendar-format leave tracker
# ----------------------------------------------------------------------------

# Each entry: name -> list of (start, end, code)
LEAVE_INTERVALS = {
    "Mo Patel":        [(date(YEAR,8,12), date(YEAR,8,19), "A"),
                         (date(YEAR,12,22), date(YEAR,12,31), "B")],
    "Priya Ramesh":    [(date(YEAR,2,3), date(YEAR,2,7), "A"),
                         (date(YEAR,10,5), date(YEAR,10,16), "B")],
    "Ananya Krishnan": [(date(YEAR,6,15), date(YEAR,6,26), "T/V")],
    "Haidi Wong":      [(date(YEAR,4,20), date(YEAR,4,24), "A"),
                         (date(YEAR,9,14), date(YEAR,9,18), "A")],
    "Karthik Iyer":    [(date(YEAR,5,1), date(YEAR,5,3), "S")],
    "Rohit Verma":     [(date(YEAR,8,10), date(YEAR,8,21), "B")],
    "Sandra Lim":      [(date(YEAR,3,9), date(YEAR,3,13), "A"),
                         (date(YEAR,9,7), date(YEAR,9,11), "A")],
    "Vikram Joshi":    [(date(YEAR,7,1), date(YEAR,7,15), "B")],
    "Meera Pillai":    [(date(YEAR,1,20), date(YEAR,1,24), "A"),
                         (date(YEAR,8,17), date(YEAR,8,21), "A")],
    "Tom Adebayo":     [(date(YEAR,4,6), date(YEAR,4,10), "A")],
    "Liu Wei":         [(date(YEAR,2,23), date(YEAR,2,27), "A"),
                         (date(YEAR,10,26), date(YEAR,10,30), "T/V")],
    "Aisha Khan":      [(date(YEAR,7,13), date(YEAR,7,24), "B")],
    "Deepak Rao":      [(date(YEAR,2,16), date(YEAR,2,20), "A"),
                         (date(YEAR,11,2), date(YEAR,11,6), "A")],
    "Elena Schmidt":   [(date(YEAR,4,27), date(YEAR,5,1), "A")],
    "Nisha Bose":      [(date(YEAR,6,8), date(YEAR,6,19), "B")],
    "Farah Ahmed":     [(date(YEAR,2,9), date(YEAR,2,13), "A"),
                         (date(YEAR,9,21), date(YEAR,9,25), "A")],
    "Jin Park":        [(date(YEAR,3,30), date(YEAR,4,3), "A")],
    "Sam O'Connor":    [(date(YEAR,8,3), date(YEAR,8,14), "B")],
}

# A handful of public holidays everyone shares (mark with "P")
PUBLIC_HOLIDAYS = [
    date(YEAR, 1, 1),    # New Year
    date(YEAR, 1, 26),   # Republic Day
    date(YEAR, 8, 15),   # Independence Day
    date(YEAR, 10, 2),   # Gandhi Jayanti
    date(YEAR, 12, 25),  # Christmas
]


def _build_year_dates():
    d = date(YEAR, 1, 1)
    end = date(YEAR, 12, 31)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


YEAR_DATES = _build_year_dates()


def _header(ws, headers):
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="305496")


def write_leave_tracker():
    """Calendar format:
       Row 1: month labels (Jan-26, Jan-26, ..., Feb-26, ...)
       Row 2: 'Auditor' + full date strings ('Thursday, January 1, 2026', ...)
       Row 3+: auditor name + leave codes per day
    """
    OUT.mkdir(exist_ok=True)
    wb = Workbook(); wb.remove(wb.active)
    for team, members in ROSTER.items():
        ws = wb.create_sheet(team)
        # Row 1: month labels
        for i, d in enumerate(YEAR_DATES, start=2):
            ws.cell(row=1, column=i, value=d.strftime("%b-%y")).font = Font(bold=True)
        # Row 2: 'Auditor' + date headers
        ws.cell(row=2, column=1, value="Auditor").font = Font(bold=True)
        for i, d in enumerate(YEAR_DATES, start=2):
            ws.cell(row=2, column=i, value=d.strftime("%A, %B %#d, %Y")
                    if hasattr(d, "strftime") else str(d)).font = Font(bold=True)
        # Data rows
        for r, (role, name) in enumerate(members, start=3):
            ws.cell(row=r, column=1, value=f"{role}/{name}")
            # Build leave map
            leave_map: dict[date, str] = {h: "P" for h in PUBLIC_HOLIDAYS}
            for s, e, code in LEAVE_INTERVALS.get(name, []):
                d = s
                while d <= e:
                    leave_map[d] = code
                    d += timedelta(days=1)
            for i, d in enumerate(YEAR_DATES, start=2):
                code = leave_map.get(d, "")
                if code:
                    ws.cell(row=r, column=i, value=code)
        ws.column_dimensions["A"].width = 26
        for i in range(2, len(YEAR_DATES) + 2):
            ws.column_dimensions[get_column_letter(i)].width = 6
        ws.freeze_panes = "B3"
    wb.save(OUT / "leave_tracker.xlsx")


def write_skills():
    OUT.mkdir(exist_ok=True)
    wb = Workbook(); wb.remove(wb.active)
    for team, members in ROSTER.items():
        ws = wb.create_sheet(team)
        _header(ws, ["Auditor", "Skills", "Certifications"])
        for role, name in members:
            sk, ce = SKILLS.get(name, ("", ""))
            ws.append([f"{role}/{name}", sk, ce])
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["C"].width = 25
    wb.save(OUT / "skills.xlsx")


# ----------------------------------------------------------------------------
# Planned audits — SINGLE sheet, full year (scheduler filters to H2)
# ----------------------------------------------------------------------------

AUDITS = [
    # (Number, Title, PrimaryTeam, ReportDate, Analytics, TotalDays, PrimaryDays, Quarter, TL)
    # H1 audits (these are also reflected in h1_allocations.xlsx)
    ("2026-GT-001", "AWS Pooled Audit", "T&A", "26/01/2026", "No", 130, 70, "Q1", "Sandra Lim"),
    ("2026-GT-002", "Active Directory & Identity Hygiene", "ICS", "16/02/2026", "No", 110, 60, "Q1", "Priya Ramesh"),
    ("2026-GT-003", "Data Lineage & Quality Controls", "DM", "23/03/2026", "Yes", 140, 75, "Q1", "Deepak Rao"),
    ("2026-GT-004", "Privileged Access Management (OneVault)", "ICS", "20/04/2026", "Yes", 160, 90, "Q2", "Mo Patel"),
    ("2026-GT-005", "Network Firewall & Segmentation Review", "T&A", "18/05/2026", "No", 120, 65, "Q2", "Vikram Joshi"),
    ("2026-GT-006", "ML Model Risk & MLOps Governance", "DM", "22/06/2026", "Yes", 150, 80, "Q2", "Elena Schmidt"),
    # H2 audits (these are what the scheduler will assign)
    ("2026-GT-007", "Ransomware & Malware Resilience", "ICS", "20/07/2026", "No", 130, 75, "Q3", "Mo Patel"),
    ("2026-GT-008", "Cloud Patching & Vulnerability Management", "T&A", "17/08/2026", "Yes", 120, 60, "Q3", "Sandra Lim"),
    ("2026-GT-009", "Data Warehouse Migration Controls", "DM", "21/09/2026", "No", 110, 60, "Q3", "Deepak Rao"),
    ("2026-GT-010", "Endpoint DLP & Sensitivity Labels", "ICS", "19/10/2026", "Yes", 100, 55, "Q4", "Priya Ramesh"),
    ("2026-GT-011", "Database Activity Monitoring (DAM) Audit", "T&A", "23/11/2026", "Yes", 130, 70, "Q4", "Vikram Joshi"),
    ("2026-GT-012", "AI Factory & LLM Red-Teaming Audit", "ICS", "14/12/2026", "Yes", 140, 80, "Q4", "Mo Patel"),
]


def write_planned_audits():
    OUT.mkdir(exist_ok=True)
    wb = Workbook(); ws = wb.active; ws.title = "All Audits"
    _header(ws, ["Audit Number", "TITLE", "Audit Primary Team",
                  "REPORT ISSUANCE PLANNED", "Analytics Used", "Total Auditor Days",
                  "Primary Audit Days", "Reporting Quarter", "Team Lead"])
    for row in AUDITS:
        ws.append(list(row))
    widths = [16, 45, 18, 22, 16, 18, 18, 18, 20]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    wb.save(OUT / "planned_audits.xlsx")


# ----------------------------------------------------------------------------
# H1 allocations — weekly grid for Jan-Jun 2026
# ----------------------------------------------------------------------------

H1_AUDITS_BY_PERSON = {
    # who worked on which H1 audit + which weeks (Monday dates)
    "Sandra Lim": [("AWS Pooled Audit", date(YEAR,1,5), date(YEAR,1,30))],
    "Mo Patel": [("PAM Audit Phase 1", date(YEAR,3,30), date(YEAR,4,17))],
    "Priya Ramesh": [("Active Directory & Identity Hygiene", date(YEAR,2,2), date(YEAR,2,13))],
    "Vikram Joshi": [("Network Firewall & Segmentation Review", date(YEAR,5,4), date(YEAR,5,15))],
    "Deepak Rao": [("Data Lineage & Quality Controls", date(YEAR,3,2), date(YEAR,3,20))],
    "Elena Schmidt": [("ML Model Risk & MLOps Governance", date(YEAR,6,8), date(YEAR,6,19))],
    "Ananya Krishnan": [("Active Directory & Identity Hygiene", date(YEAR,2,2), date(YEAR,2,13))],
    "Meera Pillai": [("AWS Pooled Audit", date(YEAR,1,5), date(YEAR,1,30))],
    "Haidi Wong": [("PAM Audit Phase 1", date(YEAR,3,30), date(YEAR,4,17))],
    "Liu Wei": [("Data Lineage & Quality Controls", date(YEAR,3,2), date(YEAR,3,20))],
    "Nisha Bose": [("Data Lineage & Quality Controls", date(YEAR,3,2), date(YEAR,3,20))],
    "Farah Ahmed": [("ML Model Risk & MLOps Governance", date(YEAR,6,8), date(YEAR,6,19))],
    "Aisha Khan": [("Network Firewall & Segmentation Review", date(YEAR,5,4), date(YEAR,5,15))],
}


def write_h1_allocations():
    OUT.mkdir(exist_ok=True)
    wb = Workbook(); wb.remove(wb.active)
    first_monday = date(YEAR, 1, 5)
    weeks = [first_monday + timedelta(weeks=i) for i in range(26)]   # H1 = 26 weeks
    months = []
    for w in weeks:
        m = w.strftime("%b-%y")
        months.append(m if (not months or months[-1] != m) else "")
    for team, members in ROSTER.items():
        ws = wb.create_sheet(team)
        # Row 1: months
        ws.cell(row=1, column=1, value="")
        for i, m in enumerate(months, start=2):
            c = ws.cell(row=1, column=i, value=m)
            if m: c.font = Font(bold=True)
        # Row 2: Auditor + week labels
        ws.cell(row=2, column=1, value="Auditor").font = Font(bold=True)
        for i, w in enumerate(weeks, start=2):
            ws.cell(row=2, column=i, value=f"{w.day}/{w.strftime('%b')}").font = Font(bold=True)
        # Data
        for r, (role, name) in enumerate(members, start=3):
            ws.cell(row=r, column=1, value=f"{role}/{name}")
            for title, s, e in H1_AUDITS_BY_PERSON.get(name, []):
                for i, w in enumerate(weeks, start=2):
                    w_end = w + timedelta(days=4)
                    if w <= e and w_end >= s:
                        cur = ws.cell(row=r, column=i).value
                        ws.cell(row=r, column=i, value=title if not cur else f"{cur}; {title}")
        ws.column_dimensions["A"].width = 28
        for i in range(2, len(weeks) + 2):
            ws.column_dimensions[get_column_letter(i)].width = 14
        ws.freeze_panes = "B3"
    wb.save(OUT / "h1_allocations.xlsx")


# ----------------------------------------------------------------------------
# Interests — SINGLE sheet, audit-row layout. Some rows include Start/End.
# ----------------------------------------------------------------------------

INTERESTS_ROWS = [
    # (SL No, Audit Team, Audit Name, Start Date, End Date, P1, P2, P3)
    (1, "ICS", "Ransomware & Malware Resilience", None, None,
     "Karthik Iyer, Rohit Verma", "Mo Patel", "Ananya Krishnan"),
    (2, "T&A", "Cloud Patching & Vulnerability Management",
     date(YEAR,7,20), date(YEAR,8,14),
     "Sandra Lim, Tom Adebayo", "Meera Pillai", "Aisha Khan"),
    (3, "DM", "Data Warehouse Migration Controls", None, None,
     "Sam O'Connor, Nisha Bose", "Deepak Rao", "Jin Park"),
    (4, "ICS", "Endpoint DLP & Sensitivity Labels", None, None,
     "Priya Ramesh, Rohit Verma", "Karthik Iyer", "Haidi Wong"),
    (5, "T&A", "Database Activity Monitoring (DAM) Audit",
     date(YEAR,10,12), date(YEAR,11,13),
     "Liu Wei, Vikram Joshi", "Tom Adebayo", "Aisha Khan"),
    (6, "ICS", "AI Factory & LLM Red-Teaming Audit",
     date(YEAR,11,2), date(YEAR,12,4),
     "Mo Patel, Ananya Krishnan", "Farah Ahmed, Elena Schmidt", "Rohit Verma"),
]


def write_interests():
    OUT.mkdir(exist_ok=True)
    wb = Workbook(); ws = wb.active; ws.title = "Interests"
    _header(ws, ["SL No", "Audit Team", "Audit Name", "Start Date", "End Date",
                  "Preference 1", "Preference 2", "Preference 3"])
    for row in INTERESTS_ROWS:
        sl, team, name, sd, ed, p1, p2, p3 = row
        ws.append([sl, team, name,
                    sd.isoformat() if sd else "",
                    ed.isoformat() if ed else "",
                    p1, p2, p3])
    widths = [8, 14, 45, 14, 14, 40, 40, 40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    wb.save(OUT / "interests.xlsx")


def main():
    write_leave_tracker()
    write_skills()
    write_planned_audits()
    write_h1_allocations()
    write_interests()
    print("Generated v2 test files in", OUT.resolve())
    for f in sorted(OUT.iterdir()):
        print(" -", f.name)


if __name__ == "__main__":
    main()
