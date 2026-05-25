"""
Audit Scheduling Assistant — v2
================================
Schedules H2 2026 audits given H1 commitments.

Inputs (in INPUT_DIR):
    leave_tracker.xlsx       - calendar format: row 1 month labels, row 2 day labels,
                               data rows = auditor + daily leave codes (A/A1/A2/B/T/V/S/O/P).
                               3 sheets (ICS, T&A, DM).
    skills.xlsx              - 3 sheets, cols: Auditor, Skills, Certifications
    planned_audits.xlsx      - SINGLE sheet, cols: Audit Number, TITLE,
                               Audit Primary Team, REPORT ISSUANCE PLANNED,
                               Analytics Used, Total Auditor Days, Primary Audit Days,
                               Reporting Quarter, Team Lead
    h1_allocations.xlsx      - calendar grid (same as scheduler grid output) showing
                               H1 2026 bookings. 3 sheets.
    interests.xlsx           - SINGLE sheet, cols: SL No, Audit Team, Audit Name,
                               Start Date, End Date, Preference 1, Preference 2, Preference 3
                               (each Preference cell holds comma-separated auditor names)

Outputs (in OUTPUT_DIR):
    assignments_grid.xlsx    - same week-grid format as h1_allocations.xlsx
    assignments_summary.xlsx - one row per audit
    warnings.xlsx            - warnings + auditor workload

Scheduling horizon: H2 2026 (1 Jul – 31 Dec 2026).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

INPUT_DIR = Path("./inputs")
OUTPUT_DIR = Path("./outputs")
CACHE_DIR = Path("./cache")
TEAMS = ["ICS", "T&A", "DM"]
SHEET_ALIASES = {
    "ICS": ["ICS", "ics", "Team ICS"],
    "T&A": ["T&A", "TA", "T and A", "Team T&A"],
    "DM": ["DM", "Team DM", "Data Management"],
}
SCHEDULE_YEAR = 2026
H2_START = date(2026, 7, 1)
H2_END = date(2026, 12, 31)
TEAM_SIZE = 4
MIN_TEAM_MEMBERS = 3
REPORTING_BUFFER_DAYS = 5
AUDIT_DAYS_PER_WEEK = 3                   # 1 working week ≈ 3 audit-days
MEMBER_FLEX_WEEKS = 2                     # members can shift start ±2 weeks within audit window
AVAILABILITY_THRESHOLD = 0.6

# Leave codes: all of these mark unavailability.
LEAVE_CODES = {"A", "A1", "A2", "B", "T/V", "T", "V", "S", "O", "P"}

# Scoring
W_SKILL = 0.35
W_PRIOR = 0.30
W_AVAIL = 0.20
W_INTEREST = 0.15

# Split
BASE_SPLIT = {"primary": 0.50, "second": 0.30, "third": 0.20}
TEAM_FLOOR = 0.15
ANALYTICS_DM_BUMP = 0.10
INFRA_TA_BUMP = 0.05
SECURITY_ICS_BUMP = 0.05

INFRA_KEYWORDS = {"aws", "azure", "gcp", "cloud", "network", "firewall", "segmentation",
                  "active directory", "ad ", "infrastructure", "datacenter", "datacentre",
                  "patching", "endpoint", "server"}
SECURITY_KEYWORDS = {"pam", "vault", "identity", "iam", "access", "privileged",
                     "red-team", "red team", "ransomware", "malware", "cyber", "ics",
                     "dlp", "encryption", "key management"}
DM_KEYWORDS = {"data", "analytics", "model", "ml ", "ai ", "report", "etl",
               "warehouse", "lineage", "quality"}

# ----------------------------------------------------------------------------
# DATA CLASSES
# ----------------------------------------------------------------------------

@dataclass
class Booking:
    audit_number: str
    audit_title: str
    start: date
    end: date
    source: str = "H2"


@dataclass
class Auditor:
    name: str
    role: str
    home_team: str
    skills: set[str] = field(default_factory=set)
    certifications: set[str] = field(default_factory=set)
    leaves: set[date] = field(default_factory=set)
    preferences: list[str] = field(default_factory=list)
    prior_audits: list[str] = field(default_factory=list)
    bookings: list[Booking] = field(default_factory=list)
    preference_satisfied: bool = False

    @property
    def is_sam(self) -> bool:
        return self.role.upper() == "SAM"

    @property
    def days_booked_h2(self) -> int:
        return sum(working_days_between(b.start, b.end)
                   for b in self.bookings if b.source == "H2")

    @property
    def assigned_h2_audits(self) -> list[str]:
        return [b.audit_number for b in self.bookings if b.source == "H2"]

    def is_busy_on(self, d: date) -> bool:
        if d in self.leaves:
            return True
        for b in self.bookings:
            if b.start <= d <= b.end:
                return True
        return False

    def has_overlap(self, start: date, end: date) -> bool:
        for b in self.bookings:
            if not (b.end < start or b.start > end):
                return True
        return False


@dataclass
class Audit:
    number: str
    title: str
    primary_team: str
    report_date: date
    analytics: bool
    total_days: int
    quarter: str
    primary_days: Optional[int] = None   # explicit primary-team allocation from input file
    suggested_lead: Optional[str] = None
    interest_start: Optional[date] = None
    interest_end: Optional[date] = None
    required_skills: set[str] = field(default_factory=set)
    required_certs: set[str] = field(default_factory=set)
    domain_tags: set[str] = field(default_factory=set)
    start_date: date = field(default=date(2026, 7, 1))
    end_date: date = field(default=date(2026, 7, 1))
    duration_calendar_days: int = 0
    team_days: dict[str, int] = field(default_factory=dict)
    team_headcount: dict[str, int] = field(default_factory=dict)
    assigned_tl: Optional[str] = None
    assigned_members: list[tuple[str, str, date, date]] = field(default_factory=list)


# ----------------------------------------------------------------------------
# UTILITIES
# ----------------------------------------------------------------------------

def working_days_between(start: date, end: date) -> int:
    days = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def working_days_before(end: date, n: int) -> date:
    d = end
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _resolve_sheet(xl: pd.ExcelFile, team: str) -> str:
    for cand in SHEET_ALIASES[team]:
        if cand in xl.sheet_names:
            return cand
    for s in xl.sheet_names:
        if team.lower().replace(" ", "") in s.lower().replace(" ", ""):
            return s
    raise KeyError(f"No sheet for team {team} in {xl.io}")


def _parse_auditor_cell(raw) -> tuple[str, str]:
    s = str(raw).strip()
    if "/" in s:
        role, name = s.split("/", 1)
        return role.strip().upper(), name.strip()
    return "AM", s


def _parse_date_header(val) -> Optional[date]:
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.date()
    s = str(val).strip()
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y", "%d %B %Y",
                "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


# ----------------------------------------------------------------------------
# LEAVE TRACKER (calendar format)
# ----------------------------------------------------------------------------

def _parse_leave_sheet(df: pd.DataFrame) -> dict[str, set[date]]:
    leaves_by_name: dict[str, set[date]] = {}
    auditor_row_idx = None
    for i in range(min(5, len(df))):
        row_vals = [str(v).strip().lower() for v in df.iloc[i].tolist()]
        if "auditor" in row_vals:
            auditor_row_idx = i
            break
    if auditor_row_idx is None:
        return leaves_by_name

    header = df.iloc[auditor_row_idx].tolist()
    date_columns: list[tuple[int, date]] = []
    for col_idx, val in enumerate(header):
        if col_idx == 0 or pd.isna(val):
            continue
        parsed = _parse_date_header(val)
        if parsed:
            date_columns.append((col_idx, parsed))
    if not date_columns:
        return leaves_by_name

    for r in range(auditor_row_idx + 1, len(df)):
        raw_name = df.iat[r, 0]
        if pd.isna(raw_name):
            continue
        _, name = _parse_auditor_cell(raw_name)
        if not name or name.lower() == "nan":
            continue
        days: set[date] = set()
        for col_idx, d in date_columns:
            cell = df.iat[r, col_idx]
            if pd.isna(cell):
                continue
            code = str(cell).strip().upper().replace(" ", "")
            if code in LEAVE_CODES:
                days.add(d)
        leaves_by_name[name] = days
    return leaves_by_name


# ----------------------------------------------------------------------------
# LOADERS
# ----------------------------------------------------------------------------

def load_auditors() -> dict[str, Auditor]:
    auditors: dict[str, Auditor] = {}

    # 1. Skills file defines the roster
    xl = pd.ExcelFile(INPUT_DIR / "skills.xlsx")
    for team in TEAMS:
        df = pd.read_excel(xl, sheet_name=_resolve_sheet(xl, team))
        df.columns = [c.strip() for c in df.columns]
        for _, row in df.iterrows():
            if pd.isna(row.get("Auditor")):
                continue
            role, name = _parse_auditor_cell(row["Auditor"])
            aud = Auditor(name=name, role=role, home_team=team)
            if pd.notna(row.get("Skills")):
                aud.skills = {s.strip().lower()
                              for s in str(row["Skills"]).split(",") if s.strip()}
            if pd.notna(row.get("Certifications")):
                aud.certifications = {c.strip().lower()
                                       for c in str(row["Certifications"]).split(",") if c.strip()}
            auditors[name] = aud

    # 2. Leave tracker
    xl = pd.ExcelFile(INPUT_DIR / "leave_tracker.xlsx")
    for team in TEAMS:
        df = pd.read_excel(xl, sheet_name=_resolve_sheet(xl, team), header=None)
        leaves = _parse_leave_sheet(df)
        for name, days in leaves.items():
            if name in auditors:
                auditors[name].leaves = days

    # 3. H1 allocations
    h1_path = INPUT_DIR / "h1_allocations.xlsx"
    if h1_path.exists():
        _load_h1_allocations(h1_path, auditors)

    # 4. Interests + window overrides
    _load_interests_and_overrides(INPUT_DIR / "interests.xlsx", auditors)

    return auditors


def _find_grid_headers(df: pd.DataFrame) -> tuple[Optional[int], Optional[int]]:
    for i in range(min(5, len(df))):
        row_vals = [str(v).strip().lower() for v in df.iloc[i].tolist()]
        if "auditor" in row_vals:
            return i, i
    return None, None


def _parse_week_label(val, year: int) -> Optional[date]:
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.date()
    s = str(val).strip()
    for fmt in ("%d/%b", "%d %b", "%d-%b", "%d/%B", "%d %B"):
        try:
            return datetime.strptime(s, fmt).date().replace(year=year)
        except ValueError:
            continue
    return _parse_date_header(val)


def _load_h1_allocations(path: Path, auditors: dict[str, Auditor]) -> None:
    xl = pd.ExcelFile(path)
    for team in TEAMS:
        try:
            sheet = _resolve_sheet(xl, team)
        except KeyError:
            continue
        df = pd.read_excel(xl, sheet_name=sheet, header=None)
        header_row, date_row = _find_grid_headers(df)
        if header_row is None:
            continue
        week_dates: list[tuple[int, date]] = []
        for col_idx in range(1, df.shape[1]):
            val = df.iat[date_row, col_idx]
            if pd.isna(val):
                continue
            wd = _parse_week_label(val, SCHEDULE_YEAR)
            if wd:
                week_dates.append((col_idx, wd))
        if not week_dates:
            continue

        for r in range(date_row + 1, len(df)):
            raw_name = df.iat[r, 0]
            if pd.isna(raw_name):
                continue
            _, name = _parse_auditor_cell(raw_name)
            if name not in auditors:
                continue
            current_title = None
            current_start = None
            current_end = None
            for col_idx, wstart in week_dates:
                cell = df.iat[r, col_idx]
                title = str(cell).strip() if pd.notna(cell) else ""
                title = re.sub(r"\(.*?\)", "", title).strip()
                if title == current_title and current_title:
                    current_end = wstart + timedelta(days=4)
                else:
                    if current_title:
                        auditors[name].bookings.append(Booking(
                            audit_number=f"H1-{current_title[:20]}",
                            audit_title=current_title,
                            start=current_start, end=current_end, source="H1",
                        ))
                        if current_title not in auditors[name].prior_audits:
                            auditors[name].prior_audits.append(current_title)
                    if title:
                        current_title = title
                        current_start = wstart
                        current_end = wstart + timedelta(days=4)
                    else:
                        current_title = None
            if current_title:
                auditors[name].bookings.append(Booking(
                    audit_number=f"H1-{current_title[:20]}",
                    audit_title=current_title,
                    start=current_start, end=current_end, source="H1",
                ))
                if current_title not in auditors[name].prior_audits:
                    auditors[name].prior_audits.append(current_title)


def _load_interests_and_overrides(path: Path, auditors: dict[str, Auditor]) -> dict:
    overrides: dict[str, tuple[Optional[date], Optional[date]]] = {}
    if not path.exists():
        _load_interests_and_overrides._overrides = overrides
        return overrides
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    def find_col(*candidates):
        cands = {x.lower() for x in candidates}
        for c in df.columns:
            if c.lower().strip() in cands:
                return c
        return None

    col_audit = find_col("Audit Name", "Audit", "Audit Number")
    col_start = find_col("Start Date", "Start")
    col_end = find_col("End Date", "End")
    pref_cols = [c for c in df.columns if c.lower().startswith("preference")]

    if col_audit is None:
        _load_interests_and_overrides._overrides = overrides
        return overrides

    for _, row in df.iterrows():
        audit_label = row.get(col_audit)
        if pd.isna(audit_label):
            continue
        audit_key = str(audit_label).strip().lower()
        sd = _parse_date_header(row[col_start]) if col_start and pd.notna(row.get(col_start)) else None
        ed = _parse_date_header(row[col_end]) if col_end and pd.notna(row.get(col_end)) else None
        if sd or ed:
            overrides[audit_key] = (sd, ed)
        for pc in pref_cols:
            cell = row.get(pc)
            if pd.isna(cell):
                continue
            for raw in str(cell).split(","):
                _, name = _parse_auditor_cell(raw)
                name = name.strip()
                if name in auditors and str(audit_label).strip() not in auditors[name].preferences:
                    auditors[name].preferences.append(str(audit_label).strip())

    _load_interests_and_overrides._overrides = overrides
    return overrides


def load_audits() -> list[Audit]:
    audits: list[Audit] = []
    xl = pd.ExcelFile(INPUT_DIR / "planned_audits.xlsx")
    df = pd.read_excel(xl, sheet_name=xl.sheet_names[0])
    df.columns = [str(c).strip() for c in df.columns]
    overrides = getattr(_load_interests_and_overrides, "_overrides", {})

    for _, row in df.iterrows():
        if pd.isna(row.get("Audit Number")):
            continue
        rd = row.get("REPORT ISSUANCE PLANNED")
        if pd.isna(rd):
            continue
        report_date = (rd.date() if isinstance(rd, (datetime, pd.Timestamp))
                       else pd.to_datetime(rd, dayfirst=True).date())
        analytics = str(row.get("Analytics Used", "")).strip().lower() in ("yes", "y", "true")
        tl = row.get("Team Lead")
        tl = None if pd.isna(tl) else str(tl).strip()

        # Optional explicit primary-team allocation. Tolerate naming variants.
        primary_days = None
        for col in df.columns:
            if col.lower().replace("-", " ").strip() in (
                "primary audit days", "primary auditor days",
                "primary team days", "primary days",
            ):
                val = row.get(col)
                if pd.notna(val):
                    try:
                        primary_days = int(round(float(val)))
                    except (ValueError, TypeError):
                        primary_days = None
                break

        audit = Audit(
            number=str(row["Audit Number"]).strip(),
            title=str(row["TITLE"]).strip(),
            primary_team=str(row["Audit Primary Team"]).strip(),
            report_date=report_date, analytics=analytics,
            total_days=int(row["Total Auditor Days"]),
            quarter=str(row.get("Reporting Quarter", "")).strip(),
            primary_days=primary_days,
            suggested_lead=tl,
        )
        for key in (audit.title.lower(), audit.number.lower()):
            if key in overrides:
                sd, ed = overrides[key]
                audit.interest_start = sd
                audit.interest_end = ed
                break
        audits.append(audit)

    return [a for a in audits
            if H2_START <= a.report_date <= H2_END + timedelta(days=60)]


# ----------------------------------------------------------------------------
# DURATION + SPLIT
# ----------------------------------------------------------------------------

def compute_duration(audit: Audit) -> None:
    if audit.interest_start and audit.interest_end:
        audit.start_date = audit.interest_start
        audit.end_date = audit.interest_end
    else:
        per_person_audit_days = max(1, round(audit.total_days / TEAM_SIZE))
        calendar_days = max(7, round(per_person_audit_days * 7 / AUDIT_DAYS_PER_WEEK))
        audit.end_date = working_days_before(audit.report_date, REPORTING_BUFFER_DAYS)
        audit.start_date = audit.end_date - timedelta(days=calendar_days - 1)
    # Clamp to H2 boundary: H2 audits cannot start before H2_START.
    if audit.start_date < H2_START:
        audit.start_date = H2_START
    audit.duration_calendar_days = (audit.end_date - audit.start_date).days + 1


def is_audit_compressed(audit: Audit) -> bool:
    """True if the H2 window is too short for the work required."""
    per_person_audit_days = max(1, round(audit.total_days / TEAM_SIZE))
    needed = round(per_person_audit_days * 7 / AUDIT_DAYS_PER_WEEK)
    return audit.duration_calendar_days < needed * 0.6


def compute_split(audit: Audit) -> None:
    title_l = audit.title.lower()
    primary = audit.primary_team
    others = [t for t in TEAMS if t != primary]
    share = {primary: BASE_SPLIT["primary"],
             others[0]: BASE_SPLIT["second"],
             others[1]: BASE_SPLIT["third"]}

    if audit.analytics and "DM" in share:
        share["DM"] += ANALYTICS_DM_BUMP
        donor = min((t for t in share if t != "DM"), key=lambda t: share[t])
        share[donor] -= ANALYTICS_DM_BUMP
    if any(kw in title_l for kw in INFRA_KEYWORDS) and "T&A" in share:
        donor = max((t for t in share if t != "T&A"), key=lambda t: share[t])
        share["T&A"] += INFRA_TA_BUMP
        share[donor] -= INFRA_TA_BUMP
    if any(kw in title_l for kw in SECURITY_KEYWORDS) and "ICS" in share:
        donor = max((t for t in share if t != "ICS"), key=lambda t: share[t])
        share["ICS"] += SECURITY_ICS_BUMP
        share[donor] -= SECURITY_ICS_BUMP

    for t in TEAMS:
        if share[t] < TEAM_FLOOR:
            deficit = TEAM_FLOOR - share[t]
            share[t] = TEAM_FLOOR
            donor = max(share, key=share.get)
            share[donor] -= deficit

    if audit.primary_days is not None:
        # Pin the primary team's allocation; distribute the remainder across the
        # other two teams in proportion to their heuristic shares.
        primary_days = max(0, min(audit.primary_days, audit.total_days))
        remainder = audit.total_days - primary_days
        other_shares = {t: share[t] for t in others}
        denom = sum(other_shares.values()) or 1.0
        raw = {primary: float(primary_days)}
        for t in others:
            raw[t] = remainder * (other_shares[t] / denom)
    else:
        raw = {t: share[t] * audit.total_days for t in TEAMS}

    rounded = {t: int(round(v)) for t, v in raw.items()}
    # Preserve the pinned primary value exactly before reconciling drift.
    if audit.primary_days is not None:
        rounded[primary] = max(0, min(audit.primary_days, audit.total_days))
    drift = audit.total_days - sum(rounded.values())
    if drift != 0:
        # When primary is pinned, only adjust the non-primary teams.
        adjustable = others if audit.primary_days is not None else TEAMS
        order = sorted(adjustable, key=lambda t: raw[t] - int(raw[t]), reverse=(drift > 0))
        for t in order:
            if drift == 0:
                break
            rounded[t] += 1 if drift > 0 else -1
            drift += -1 if drift > 0 else 1
    audit.team_days = rounded

    per_person = max(1, round(audit.total_days / TEAM_SIZE))
    audit.team_headcount = {
        t: max(1, round(rounded[t] / per_person)) if rounded[t] > 0 else 0
        for t in TEAMS
    }
    total = sum(audit.team_headcount.values())
    while total > TEAM_SIZE:
        donor = max((t for t in TEAMS if audit.team_headcount[t] > 1),
                    key=lambda t: audit.team_headcount[t], default=None)
        if donor is None:
            break
        audit.team_headcount[donor] -= 1
        total -= 1
    while total < MIN_TEAM_MEMBERS:
        recv = max(TEAMS, key=lambda t: audit.team_days[t])
        audit.team_headcount[recv] += 1
        total += 1


# ----------------------------------------------------------------------------
# SKILL INFERENCE
# ----------------------------------------------------------------------------

SKILL_CACHE_FILE = CACHE_DIR / "skill_inference.json"


# Extended keyword vocabulary for keyword-only inference (no LLM dependency).
# Each entry maps a keyword to (skills_to_add, tag).
EXTRA_SKILL_MAP = {
    # Identity / access
    "pam": (["pam", "privileged access"], "identity"),
    "vault": (["vault", "secrets management"], "identity"),
    "onevault": (["pam", "onevault"], "identity"),
    "hashicorp": (["vault", "hashicorp"], "identity"),
    "identity": (["iam", "identity"], "identity"),
    "iam": (["iam"], "identity"),
    "access": (["access management"], "identity"),
    "privileged": (["pam", "privileged access"], "identity"),
    "active directory": (["active directory"], "identity"),
    # Cloud
    "aws": (["aws", "cloud"], "cloud"),
    "azure": (["azure", "cloud"], "cloud"),
    "gcp": (["gcp", "cloud"], "cloud"),
    "cloud": (["cloud"], "cloud"),
    "kubernetes": (["kubernetes", "containers"], "cloud"),
    "terraform": (["terraform", "iac"], "cloud"),
    # Network
    "network": (["network"], "network"),
    "firewall": (["firewall"], "network"),
    "segmentation": (["network segmentation"], "network"),
    # Data / Analytics
    "data": (["data"], "data"),
    "analytics": (["data analytics", "sql"], "data"),
    "warehouse": (["data warehouse", "sql"], "data"),
    "lineage": (["data lineage"], "data"),
    "quality": (["data quality"], "data"),
    "etl": (["etl"], "data"),
    "dam": (["database activity monitoring", "sql"], "data"),
    "database": (["database", "sql"], "data"),
    # Security operations
    "ransomware": (["ransomware", "incident response"], "security"),
    "malware": (["malware analysis"], "security"),
    "endpoint": (["endpoint", "edr"], "security"),
    "edr": (["edr"], "security"),
    "dlp": (["dlp", "data protection"], "security"),
    "red-team": (["red-teaming", "owasp"], "security"),
    "red team": (["red-teaming", "owasp"], "security"),
    "owasp": (["owasp"], "security"),
    "vulnerability": (["vulnerability management"], "security"),
    "patching": (["patching", "vulnerability management"], "infrastructure"),
    "cyber": (["cyber"], "security"),
    # AI / ML
    "llm": (["llm security", "ai/ml"], "security"),
    "ai factory": (["ai/ml", "llm security"], "security"),
    "ml model": (["ml", "mlops"], "data"),
    "mlops": (["mlops"], "data"),
    # Infrastructure
    "infrastructure": (["infrastructure"], "infrastructure"),
    "server": (["server administration"], "infrastructure"),
    "datacenter": (["datacenter"], "infrastructure"),
    "sccm": (["sccm"], "infrastructure"),
}


def infer_skills_for_audits(audits: list[Audit]) -> None:
    """Keyword-based inference. No external API calls.
    Cached to disk so manual edits to the cache JSON are respected on rerun."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache = json.loads(SKILL_CACHE_FILE.read_text()) if SKILL_CACHE_FILE.exists() else {}
    for a in audits:
        if a.number in cache:
            entry = cache[a.number]
        else:
            entry = _keyword_infer(a.title)
            cache[a.number] = entry
        a.required_skills = set(entry.get("skills", []))
        a.required_certs = set(entry.get("certs", []))
        a.domain_tags = set(entry.get("tags", []))
    SKILL_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def _keyword_infer(title: str) -> dict:
    t = title.lower()
    skills: set[str] = set()
    tags: set[str] = set()
    # Apply the extended map first (more specific terms)
    for kw, (sks, tag) in EXTRA_SKILL_MAP.items():
        if kw in t:
            skills.update(sks)
            tags.add(tag)
    # Fall back to the original broad keyword sets
    for kw in INFRA_KEYWORDS:
        if kw in t:
            skills.add(kw.strip()); tags.add("infrastructure")
    for kw in SECURITY_KEYWORDS:
        if kw in t:
            skills.add(kw.strip()); tags.add("security")
    for kw in DM_KEYWORDS:
        if kw in t:
            skills.add(kw.strip()); tags.add("data")
    return {"skills": sorted(skills), "certs": [], "tags": sorted(tags)}


# ----------------------------------------------------------------------------
# AVAILABILITY + SCORING
# ----------------------------------------------------------------------------

def availability_in_window(auditor: Auditor, start: date, end: date) -> float:
    total = working_days_between(start, end)
    if total == 0:
        return 0.0
    busy = 0
    d = start
    while d <= end:
        if d.weekday() < 5 and auditor.is_busy_on(d):
            busy += 1
        d += timedelta(days=1)
    return max(0.0, (total - busy) / total)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def prior_match(auditor: Auditor, audit: Audit) -> float:
    if not auditor.prior_audits:
        return 0.0
    stop = {"audit", "of", "and", "the", "a"}
    cur_tokens = set(re.findall(r"\w+", audit.title.lower())) - stop
    best = 0.0
    for prior in auditor.prior_audits:
        prior_tokens = set(re.findall(r"\w+", prior.lower())) - stop
        best = max(best, jaccard(cur_tokens, prior_tokens))
    return best


def score(auditor: Auditor, audit: Audit,
          window: Optional[tuple[date, date]] = None) -> tuple[float, dict]:
    skill = jaccard(auditor.skills, audit.required_skills)
    if audit.required_certs and auditor.certifications & audit.required_certs:
        skill = min(1.0, skill + 0.15)
    prior = prior_match(auditor, audit)
    if window:
        avail = availability_in_window(auditor, *window)
    else:
        avail = availability_in_window(auditor, audit.start_date, audit.end_date)
    interest = 1.0 if (audit.number in auditor.preferences
                        or audit.title in auditor.preferences) else 0.0
    total = (W_SKILL * skill + W_PRIOR * prior
             + W_AVAIL * avail + W_INTEREST * interest)
    return total, {"skill": skill, "prior": prior, "avail": avail, "interest": interest}


# ----------------------------------------------------------------------------
# WINDOW PLACEMENT FOR MEMBERS
# ----------------------------------------------------------------------------

def _find_member_window(auditor: Auditor, audit: Audit, audit_days_share: int
                        ) -> Optional[tuple[date, date]]:
    desired_days = max(5, round(audit_days_share * 7 / AUDIT_DAYS_PER_WEEK))
    # Cap the slot to the audit's actual window length — useful for compressed audits.
    max_slot = audit.duration_calendar_days
    calendar_days = min(desired_days, max_slot)
    earliest = max(H2_START, audit.start_date - timedelta(weeks=MEMBER_FLEX_WEEKS))
    latest_start = audit.end_date - timedelta(days=calendar_days - 1)

    best_slot = None
    best_avail = -1.0
    cur = earliest
    while cur <= latest_start:
        slot_end = cur + timedelta(days=calendar_days - 1)
        if not auditor.has_overlap(cur, slot_end):
            avail = availability_in_window(auditor, cur, slot_end)
            if avail > best_avail:
                best_avail = avail
                best_slot = (cur, slot_end)
        cur += timedelta(days=7)

    if best_slot and best_avail >= AVAILABILITY_THRESHOLD:
        return best_slot
    return None


# ----------------------------------------------------------------------------
# SOLVER
# ----------------------------------------------------------------------------

def solve(auditors: dict[str, Auditor], audits: list[Audit]) -> list[str]:
    warnings: list[str] = []
    audits_sorted = sorted(audits, key=lambda a: a.report_date)

    for audit in audits_sorted:
        if is_audit_compressed(audit):
            warnings.append(
                f"{audit.number} ({audit.title}): COMPRESSED — window "
                f"{audit.duration_calendar_days} days is too short for "
                f"{audit.total_days} auditor-days. Consider starting in H1 or splitting."
            )
        # ----- TL: SAM in primary, no overlap, available full window
        candidates = [
            a for a in auditors.values()
            if a.is_sam and a.home_team == audit.primary_team
            and not a.has_overlap(audit.start_date, audit.end_date)
            and availability_in_window(a, audit.start_date, audit.end_date) >= AVAILABILITY_THRESHOLD
        ]
        chosen_tl = None
        if audit.suggested_lead:
            for s in candidates:
                if s.name.lower() == audit.suggested_lead.lower():
                    chosen_tl = s
                    break
        if chosen_tl is None and candidates:
            chosen_tl = max(candidates, key=lambda s: score(s, audit)[0])

        if chosen_tl is None:
            warnings.append(
                f"{audit.number} ({audit.title}): no available SAM in {audit.primary_team} "
                f"for {audit.start_date} → {audit.end_date}"
            )
            continue

        chosen_tl.bookings.append(Booking(
            audit_number=audit.number, audit_title=audit.title,
            start=audit.start_date, end=audit.end_date, source="H2",
        ))
        audit.assigned_tl = chosen_tl.name
        if audit.number in chosen_tl.preferences or audit.title in chosen_tl.preferences:
            chosen_tl.preference_satisfied = True

        # ----- Members per team, with flexible windows
        for team in TEAMS:
            need = audit.team_headcount[team]
            if team == audit.primary_team:
                need -= 1
            if need <= 0:
                continue

            audit_days_share = audit.team_days[team] // max(1, audit.team_headcount[team])
            pool = [a for a in auditors.values()
                    if a.home_team == team and a.name != chosen_tl.name
                    and a.name not in [m[0] for m in audit.assigned_members]]

            def sort_key(a: Auditor):
                base, _ = score(a, audit)
                pref_bonus = (0.5 if ((audit.number in a.preferences or audit.title in a.preferences)
                                        and not a.preference_satisfied) else 0.0)
                workload_penalty = -0.002 * a.days_booked_h2
                return -(base + pref_bonus + workload_penalty)
            pool.sort(key=sort_key)

            picked = 0
            for cand in pool:
                if picked >= need:
                    break
                slot = _find_member_window(cand, audit, audit_days_share)
                if slot is None:
                    continue
                slot_start, slot_end = slot
                cand.bookings.append(Booking(
                    audit_number=audit.number, audit_title=audit.title,
                    start=slot_start, end=slot_end, source="H2",
                ))
                audit.assigned_members.append((cand.name, cand.home_team, slot_start, slot_end))
                if audit.number in cand.preferences or audit.title in cand.preferences:
                    cand.preference_satisfied = True
                picked += 1

            if picked < need:
                warnings.append(
                    f"{audit.number} ({audit.title}): only filled {picked}/{need} from {team}"
                )

    unsatisfied = [a.name for a in auditors.values()
                   if a.preferences and not a.preference_satisfied]
    if unsatisfied:
        warnings.append(f"Preferred audit not assigned: {', '.join(unsatisfied)}")

    return warnings


# ----------------------------------------------------------------------------
# WRITERS
# ----------------------------------------------------------------------------

def write_grid(auditors: dict[str, Auditor], audits: list[Audit], path: Path) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    first_monday = monday_of(date(SCHEDULE_YEAR, 1, 1))
    if first_monday.year < SCHEDULE_YEAR:
        first_monday += timedelta(days=7)
    weeks = [first_monday + timedelta(weeks=i) for i in range(52)]
    months = []
    for w in weeks:
        m = w.strftime("%b-%y")
        months.append(m if (not months or months[-1] != m) else "")

    for team in TEAMS:
        ws = wb.create_sheet(team)
        for i, m in enumerate(months, start=2):
            c = ws.cell(row=1, column=i, value=m)
            if m:
                c.font = Font(bold=True)
        ws.cell(row=2, column=1, value="Auditor").font = Font(bold=True)
        for i, w in enumerate(weeks, start=2):
            ws.cell(row=2, column=i, value=f"{w.day}/{w.strftime('%b')}").font = Font(bold=True)

        team_auditors = sorted(
            [a for a in auditors.values() if a.home_team == team],
            key=lambda x: (x.role != "SAM", x.role, x.name),
        )
        for r, aud in enumerate(team_auditors, start=3):
            ws.cell(row=r, column=1, value=f"{aud.role}/{aud.name}")
            for i, w in enumerate(weeks, start=2):
                week_end = w + timedelta(days=4)
                titles = [b.audit_title for b in aud.bookings
                          if b.start <= week_end and b.end >= w]
                if titles:
                    c = ws.cell(row=r, column=i, value="; ".join(titles))
                    is_h2 = any(b.source == "H2" and b.start <= week_end and b.end >= w
                                for b in aud.bookings)
                    c.fill = PatternFill("solid",
                                          start_color="C6E5B3" if is_h2 else "E8E8E8")
        ws.freeze_panes = "B3"
        ws.column_dimensions["A"].width = 28
        for i in range(2, len(weeks) + 2):
            ws.column_dimensions[get_column_letter(i)].width = 14
    wb.save(path)


def write_summary(audits: list[Audit], auditors: dict[str, Auditor], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    headers = ["Audit Number", "Title", "Primary Team", "Report Date",
               "Window", "Total Days", "Split (ICS/T&A/DM)",
               "Headcount (ICS/T&A/DM)", "Team Lead",
               "Members (name + window)", "Avg Skill Score", "Warnings"]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="305496")
        c.alignment = Alignment(horizontal="center")
    for r, a in enumerate(audits, start=2):
        scores = []
        if a.assigned_tl and a.assigned_tl in auditors:
            scores.append(score(auditors[a.assigned_tl], a)[1]["skill"])
        for m_name, _, _, _ in a.assigned_members:
            if m_name in auditors:
                scores.append(score(auditors[m_name], a)[1]["skill"])
        avg = round(sum(scores)/len(scores), 2) if scores else 0.0
        warns = []
        if not a.assigned_tl: warns.append("no TL")
        if len(a.assigned_members) + (1 if a.assigned_tl else 0) < MIN_TEAM_MEMBERS:
            warns.append("understaffed")
        members_str = "; ".join(
            f"{n} [{s.strftime('%d %b')}–{e.strftime('%d %b')}]"
            for n, _, s, e in a.assigned_members)
        for col, val in enumerate([
            a.number, a.title, a.primary_team, a.report_date.isoformat(),
            f"{a.start_date.strftime('%d %b')} → {a.end_date.strftime('%d %b')}",
            a.total_days,
            f"{a.team_days.get('ICS',0)}/{a.team_days.get('T&A',0)}/{a.team_days.get('DM',0)}",
            f"{a.team_headcount.get('ICS',0)}/{a.team_headcount.get('T&A',0)}/{a.team_headcount.get('DM',0)}",
            a.assigned_tl or "—", members_str, avg, ", ".join(warns),
        ], start=1):
            ws.cell(row=r, column=col, value=val)
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 22
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["J"].width = 60
    ws.freeze_panes = "A2"
    wb.save(path)


def write_warnings(warnings: list[str], auditors: dict[str, Auditor], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Warnings"
    ws.cell(row=1, column=1, value="Detail").font = Font(bold=True)
    for r, w in enumerate(warnings, start=2):
        ws.cell(row=r, column=1, value=w)
    ws.column_dimensions["A"].width = 100

    ws2 = wb.create_sheet("Workload (H2)")
    ws2.append(["Auditor", "Role", "Team", "H2 Audits", "H2 Days Booked", "Preference Met"])
    for a in sorted(auditors.values(), key=lambda x: (x.home_team, x.role, x.name)):
        ws2.append([
            a.name, a.role, a.home_team,
            len(a.assigned_h2_audits), a.days_booked_h2,
            "yes" if a.preference_satisfied else ("n/a" if not a.preferences else "no"),
        ])
    for col in range(1, 7):
        ws2.column_dimensions[get_column_letter(col)].width = 22
    wb.save(path)


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    print("Loading auditors...")
    auditors = load_auditors()
    print(f"  → {len(auditors)} auditors")
    print("Loading H2 audits...")
    audits = load_audits()
    print(f"  → {len(audits)} H2 audits")
    for a in audits:
        compute_duration(a); compute_split(a)
    infer_skills_for_audits(audits)
    warnings = solve(auditors, audits)
    print(f"  → {len(warnings)} warnings")
    write_grid(auditors, audits, OUTPUT_DIR / "assignments_grid.xlsx")
    write_summary(audits, auditors, OUTPUT_DIR / "assignments_summary.xlsx")
    write_warnings(warnings, auditors, OUTPUT_DIR / "warnings.xlsx")
    print("Done.")


if __name__ == "__main__":
    main()
