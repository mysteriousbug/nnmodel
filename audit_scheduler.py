"""
Audit Scheduling Assistant
==========================
Inputs (all in INPUT_DIR):
    leave_tracker.xlsx       - 3 sheets (ICS, T&A, DM), cols: Auditor, Planned_Leaves
    skills.xlsx              - 3 sheets, cols: Auditor, Skills, Certifications
    planned_audits.xlsx      - 3 sheets, cols: Audit Number, TITLE, Audit Primary Team,
                               REPORT ISSUANCE PLANNED, Analytics Used, Total Auditor Days,
                               Reporting Quarter, Team Lead
    planned_assignments.xlsx - 3 sheets, week-grid of prior assignments
    interests.xlsx           - 3 sheets, cols: Auditor, Audit_Preference1..3

Outputs (in OUTPUT_DIR):
    assignments_grid.xlsx    - same week-grid format as planned_assignments.xlsx
    assignments_summary.xlsx - one row per audit: TL, members, team split, scores
    warnings.xlsx            - capacity/skill/leave/preference warnings

Run:
    export GROQ_API_KEY=...
    python audit_scheduler.py
"""

from __future__ import annotations

import json
import os
import re
import sys
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
SHEET_ALIASES = {  # tolerate small naming variations
    "ICS": ["ICS", "ics", "Team ICS"],
    "T&A": ["T&A", "TA", "T and A", "Team T&A"],
    "DM": ["DM", "Team DM", "Data Management"],
}
SCHEDULE_YEAR = 2026
TEAM_SIZE = 4                          # 1 TL + 3 members
MIN_TEAM_MEMBERS = 3
WORKING_DAYS_PER_WEEK = 5
REPORTING_BUFFER_DAYS = 5              # 1 working week before report date

# Scoring weights
W_SKILL = 0.35
W_PRIOR = 0.30
W_AVAIL = 0.20
W_INTEREST = 0.15

# Split heuristic
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

LLM_MODEL = "llama-3.3-70b-versatile"
LLM_TIMEOUT = 60

# ----------------------------------------------------------------------------
# DATA CLASSES
# ----------------------------------------------------------------------------

@dataclass
class Auditor:
    name: str
    role: str                          # SAM | AM | Co-Source
    home_team: str                     # ICS | T&A | DM
    skills: set[str] = field(default_factory=set)
    certifications: set[str] = field(default_factory=set)
    leaves: list[tuple[date, date]] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    prior_audits: list[str] = field(default_factory=list)
    assigned_audits: list[str] = field(default_factory=list)
    days_booked: int = 0
    preference_satisfied: bool = False

    @property
    def is_sam(self) -> bool:
        return self.role.upper() == "SAM"


@dataclass
class Audit:
    number: str
    title: str
    primary_team: str
    report_date: date
    analytics: bool
    total_days: int
    quarter: str
    suggested_lead: Optional[str] = None
    required_skills: set[str] = field(default_factory=set)
    required_certs: set[str] = field(default_factory=set)
    domain_tags: set[str] = field(default_factory=set)
    start_date: date = field(default=date(2026, 1, 1))
    end_date: date = field(default=date(2026, 1, 1))
    duration_days: int = 0
    team_days: dict[str, int] = field(default_factory=dict)
    team_headcount: dict[str, int] = field(default_factory=dict)
    assigned_tl: Optional[str] = None
    assigned_members: list[tuple[str, str, int]] = field(default_factory=list)
    # (auditor_name, home_team, days)


# ----------------------------------------------------------------------------
# LOADERS
# ----------------------------------------------------------------------------

def _resolve_sheet(xl: pd.ExcelFile, team: str) -> str:
    for candidate in SHEET_ALIASES[team]:
        if candidate in xl.sheet_names:
            return candidate
    # fallback: case-insensitive contains
    for s in xl.sheet_names:
        if team.lower().replace(" ", "") in s.lower().replace(" ", ""):
            return s
    raise KeyError(f"No sheet for team {team} in {xl.io}")


def _parse_auditor_cell(raw: str) -> tuple[str, str]:
    """'SAM/AuditorName1' -> ('SAM', 'AuditorName1'). Tolerates spaces."""
    s = str(raw).strip()
    if "/" in s:
        role, name = s.split("/", 1)
        return role.strip().upper(), name.strip()
    return "AM", s  # default if role missing


def _parse_leave_range(token: str, year: int) -> Optional[tuple[date, date]]:
    """'12 Aug-14 Aug' or '30 Oct-12 Nov' -> (date, date). Assumes given year."""
    token = token.strip().replace("–", "-").replace("—", "-")
    if not token or "-" not in token:
        return None
    left, right = [p.strip() for p in token.split("-", 1)]
    def parse_one(s: str, fallback_month: Optional[str]) -> Optional[date]:
        s = s.strip()
        # accept '12 Aug', '12 Aug 2026', 'Aug 12'
        for fmt in ("%d %b %Y", "%d %b", "%b %d", "%d %B %Y", "%d %B", "%B %d"):
            try:
                d = datetime.strptime(s, fmt).date()
                if "%Y" not in fmt:
                    d = d.replace(year=year)
                return d
            except ValueError:
                continue
        # day-only with fallback month from right side
        if fallback_month and re.fullmatch(r"\d{1,2}", s):
            try:
                return datetime.strptime(f"{s} {fallback_month} {year}", "%d %b %Y").date()
            except ValueError:
                return None
        return None
    # detect month on right side to use as fallback for left if needed
    right_month_match = re.search(r"[A-Za-z]+", right)
    fallback_month = right_month_match.group(0)[:3] if right_month_match else None
    start = parse_one(left, fallback_month)
    end = parse_one(right, None)
    if start and end and end >= start:
        return (start, end)
    return None


def load_auditors() -> dict[str, Auditor]:
    """Build the unified auditor pool from leaves + skills + interests."""
    auditors: dict[str, Auditor] = {}

    # 1. Leaves (defines who exists)
    xl = pd.ExcelFile(INPUT_DIR / "leave_tracker.xlsx")
    for team in TEAMS:
        df = pd.read_excel(xl, sheet_name=_resolve_sheet(xl, team))
        df.columns = [c.strip() for c in df.columns]
        for _, row in df.iterrows():
            if pd.isna(row.get("Auditor")):
                continue
            role, name = _parse_auditor_cell(row["Auditor"])
            aud = Auditor(name=name, role=role, home_team=team)
            raw_leaves = row.get("Planned_Leaves")
            if pd.notna(raw_leaves):
                for tok in str(raw_leaves).split(","):
                    rng = _parse_leave_range(tok, SCHEDULE_YEAR)
                    if rng:
                        aud.leaves.append(rng)
            auditors[name] = aud

    # 2. Skills
    xl = pd.ExcelFile(INPUT_DIR / "skills.xlsx")
    for team in TEAMS:
        df = pd.read_excel(xl, sheet_name=_resolve_sheet(xl, team))
        df.columns = [c.strip() for c in df.columns]
        for _, row in df.iterrows():
            if pd.isna(row.get("Auditor")):
                continue
            _, name = _parse_auditor_cell(row["Auditor"])
            if name not in auditors:
                continue
            if pd.notna(row.get("Skills")):
                auditors[name].skills = {
                    s.strip().lower() for s in str(row["Skills"]).split(",") if s.strip()
                }
            if pd.notna(row.get("Certifications")):
                auditors[name].certifications = {
                    c.strip().lower() for c in str(row["Certifications"]).split(",") if c.strip()
                }

    # 3. Interests
    xl = pd.ExcelFile(INPUT_DIR / "interests.xlsx")
    for team in TEAMS:
        df = pd.read_excel(xl, sheet_name=_resolve_sheet(xl, team))
        df.columns = [c.strip() for c in df.columns]
        pref_cols = [c for c in df.columns if c.lower().startswith("audit_preference")]
        for _, row in df.iterrows():
            if pd.isna(row.get("Auditor")):
                continue
            _, name = _parse_auditor_cell(row["Auditor"])
            if name not in auditors:
                continue
            prefs = [str(row[c]).strip() for c in pref_cols if pd.notna(row.get(c))]
            auditors[name].preferences = prefs

    # 4. Prior audits from planned_assignments.xlsx (extract distinct audit names)
    xl = pd.ExcelFile(INPUT_DIR / "planned_assignments.xlsx")
    for team in TEAMS:
        df = pd.read_excel(xl, sheet_name=_resolve_sheet(xl, team))
        df.columns = [str(c).strip() for c in df.columns]
        first_col = df.columns[0]
        for _, row in df.iterrows():
            if pd.isna(row[first_col]):
                continue
            _, name = _parse_auditor_cell(row[first_col])
            if name not in auditors:
                continue
            seen: set[str] = set()
            for col in df.columns[1:]:
                val = row[col]
                if pd.notna(val):
                    cleaned = re.sub(r"\(.*?\)", "", str(val)).strip()
                    if cleaned and cleaned.lower() != "nan":
                        seen.add(cleaned)
            auditors[name].prior_audits = sorted(seen)

    return auditors


def load_audits() -> list[Audit]:
    audits: list[Audit] = []
    xl = pd.ExcelFile(INPUT_DIR / "planned_audits.xlsx")
    for team in TEAMS:
        df = pd.read_excel(xl, sheet_name=_resolve_sheet(xl, team))
        df.columns = [str(c).strip() for c in df.columns]
        for _, row in df.iterrows():
            if pd.isna(row.get("Audit Number")):
                continue
            rd_raw = row.get("REPORT ISSUANCE PLANNED")
            if pd.isna(rd_raw):
                continue
            if isinstance(rd_raw, (datetime, pd.Timestamp)):
                report_date = rd_raw.date()
            else:
                report_date = pd.to_datetime(rd_raw, dayfirst=True).date()
            analytics = str(row.get("Analytics Used", "")).strip().lower() in ("yes", "y", "true")
            tl_raw = row.get("Team Lead")
            tl = None if pd.isna(tl_raw) else str(tl_raw).strip()
            audits.append(Audit(
                number=str(row["Audit Number"]).strip(),
                title=str(row["TITLE"]).strip(),
                primary_team=str(row["Audit Primary Team"]).strip(),
                report_date=report_date,
                analytics=analytics,
                total_days=int(row["Total Auditor Days"]),
                quarter=str(row.get("Reporting Quarter", "")).strip(),
                suggested_lead=tl,
            ))
    # de-duplicate by audit number (same audit may appear in each team's sheet)
    seen: dict[str, Audit] = {}
    for a in audits:
        if a.number not in seen:
            seen[a.number] = a
    return list(seen.values())


# ----------------------------------------------------------------------------
# DURATION + SPLIT
# ----------------------------------------------------------------------------

def working_days_before(end: date, n: int) -> date:
    d = end
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def compute_duration(audit: Audit) -> None:
    """total_days / 4 working days, ending REPORTING_BUFFER_DAYS before report."""
    fieldwork_days = max(1, round(audit.total_days / TEAM_SIZE))
    audit.duration_days = fieldwork_days
    audit.end_date = working_days_before(audit.report_date, REPORTING_BUFFER_DAYS)
    audit.start_date = working_days_before(audit.end_date, fieldwork_days - 1)


def compute_split(audit: Audit) -> None:
    """Apply 50/30/20 + keyword adjustments + 15% floor."""
    title_l = audit.title.lower()
    primary = audit.primary_team
    others = [t for t in TEAMS if t != primary]

    share = {primary: BASE_SPLIT["primary"],
             others[0]: BASE_SPLIT["second"],
             others[1]: BASE_SPLIT["third"]}

    if audit.analytics and "DM" in share:
        share["DM"] += ANALYTICS_DM_BUMP
        # take from the smallest non-DM share
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

    # apply floor
    for t in TEAMS:
        if share[t] < TEAM_FLOOR:
            deficit = TEAM_FLOOR - share[t]
            share[t] = TEAM_FLOOR
            donor = max(share, key=share.get)
            share[donor] -= deficit

    # convert to integer days that sum exactly to total_days
    raw = {t: share[t] * audit.total_days for t in TEAMS}
    rounded = {t: int(round(v)) for t, v in raw.items()}
    drift = audit.total_days - sum(rounded.values())
    if drift != 0:
        # apply drift to the team with the largest fractional remainder
        order = sorted(TEAMS, key=lambda t: raw[t] - int(raw[t]), reverse=(drift > 0))
        for t in order:
            if drift == 0:
                break
            rounded[t] += 1 if drift > 0 else -1
            drift += -1 if drift > 0 else 1
    audit.team_days = rounded

    # headcount per team: round(team_days / duration), min 1 if team has any days
    audit.team_headcount = {
        t: max(1, round(rounded[t] / audit.duration_days)) if rounded[t] > 0 else 0
        for t in TEAMS
    }
    # ensure total members in 3..4 range (TEAM_SIZE = 4)
    total = sum(audit.team_headcount.values())
    while total > TEAM_SIZE:
        donor = max((t for t in TEAMS if audit.team_headcount[t] > 1), key=lambda t: audit.team_headcount[t], default=None)
        if donor is None:
            break
        audit.team_headcount[donor] -= 1
        total -= 1
    while total < MIN_TEAM_MEMBERS:
        recv = max(TEAMS, key=lambda t: audit.team_days[t])
        audit.team_headcount[recv] += 1
        total += 1


# ----------------------------------------------------------------------------
# SKILL INFERENCE (Groq)
# ----------------------------------------------------------------------------

SKILL_CACHE_FILE = CACHE_DIR / "skill_inference.json"


def infer_skills_for_audits(audits: list[Audit]) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    cache: dict = {}
    if SKILL_CACHE_FILE.exists():
        cache = json.loads(SKILL_CACHE_FILE.read_text())

    api_key = os.environ.get("GROQ_API_KEY")
    use_llm = bool(api_key)
    if not use_llm:
        print("[skill-infer] GROQ_API_KEY not set — using keyword fallback only.", file=sys.stderr)

    for a in audits:
        if a.number in cache:
            entry = cache[a.number]
            a.required_skills = set(entry.get("skills", []))
            a.required_certs = set(entry.get("certs", []))
            a.domain_tags = set(entry.get("tags", []))
            continue

        if use_llm:
            entry = _groq_infer(a.title, a.analytics, a.primary_team, api_key)
        else:
            entry = _keyword_infer(a.title)

        cache[a.number] = entry
        a.required_skills = set(entry.get("skills", []))
        a.required_certs = set(entry.get("certs", []))
        a.domain_tags = set(entry.get("tags", []))

    SKILL_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def _keyword_infer(title: str) -> dict:
    t = title.lower()
    skills, tags = set(), set()
    for kw in INFRA_KEYWORDS:
        if kw in t:
            skills.add(kw.strip())
            tags.add("infrastructure")
    for kw in SECURITY_KEYWORDS:
        if kw in t:
            skills.add(kw.strip())
            tags.add("security")
    for kw in DM_KEYWORDS:
        if kw in t:
            skills.add(kw.strip())
            tags.add("data")
    return {"skills": sorted(skills), "certs": [], "tags": sorted(tags)}


def _groq_infer(title: str, analytics: bool, primary_team: str, api_key: str) -> dict:
    import urllib.request
    prompt = f"""You are categorising an internal audit for a global bank.
Audit title: "{title}"
Primary team: {primary_team}
Analytics used: {analytics}

Return STRICT JSON with three keys:
- "skills": list of 3-7 short skill names (lowercase, e.g. "python", "aws", "active directory", "red-teaming")
- "certs": list of relevant certifications (e.g. "cisa", "cissp", "icaew")
- "tags": list of 2-4 broad domain tags from {{infrastructure, security, data, identity, cloud, network, application, governance}}

JSON only, no prose."""
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            payload = json.loads(resp.read())
        text = payload["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        return {
            "skills": [s.lower() for s in parsed.get("skills", [])],
            "certs": [c.lower() for c in parsed.get("certs", [])],
            "tags": [t.lower() for t in parsed.get("tags", [])],
        }
    except Exception as e:
        print(f"[skill-infer] Groq failed for {title!r}: {e} — falling back to keywords.", file=sys.stderr)
        return _keyword_infer(title)


# ----------------------------------------------------------------------------
# AVAILABILITY + SCORING
# ----------------------------------------------------------------------------

def working_days_between(start: date, end: date) -> int:
    days = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def availability_ratio(auditor: Auditor, audit: Audit) -> float:
    total = working_days_between(audit.start_date, audit.end_date)
    if total == 0:
        return 0.0
    on_leave = 0
    d = audit.start_date
    while d <= audit.end_date:
        if d.weekday() < 5 and any(ls <= d <= le for ls, le in auditor.leaves):
            on_leave += 1
        d += timedelta(days=1)
    return max(0.0, (total - on_leave) / total)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def prior_match(auditor: Auditor, audit: Audit) -> float:
    """Token overlap between this audit's title and the auditor's prior audits."""
    if not auditor.prior_audits:
        return 0.0
    cur_tokens = set(re.findall(r"\w+", audit.title.lower())) - {"audit", "of", "and", "the"}
    best = 0.0
    for prior in auditor.prior_audits:
        prior_tokens = set(re.findall(r"\w+", prior.lower())) - {"audit", "of", "and", "the"}
        score = jaccard(cur_tokens, prior_tokens)
        if score > best:
            best = score
    return best


def score(auditor: Auditor, audit: Audit) -> tuple[float, dict]:
    skill = jaccard(auditor.skills, audit.required_skills)
    if audit.required_certs and auditor.certifications & audit.required_certs:
        skill = min(1.0, skill + 0.15)
    prior = prior_match(auditor, audit)
    avail = availability_ratio(auditor, audit)
    interest = 1.0 if audit.number in auditor.preferences else 0.0
    total = (W_SKILL * skill + W_PRIOR * prior + W_AVAIL * avail + W_INTEREST * interest)
    return total, {"skill": skill, "prior": prior, "avail": avail, "interest": interest}


# ----------------------------------------------------------------------------
# SOLVER
# ----------------------------------------------------------------------------

def solve(auditors: dict[str, Auditor], audits: list[Audit]) -> list[str]:
    """Greedy: earliest report date first; TL from primary team; respect splits."""
    warnings: list[str] = []
    audits_sorted = sorted(audits, key=lambda a: a.report_date)

    for audit in audits_sorted:
        # Pick TL from Primary Team SAMs
        sam_pool = [a for a in auditors.values()
                    if a.is_sam and a.home_team == audit.primary_team
                    and availability_ratio(a, audit) >= 0.6]
        if audit.suggested_lead:
            for s in sam_pool:
                if s.name.lower() == audit.suggested_lead.lower():
                    audit.assigned_tl = s.name
                    s.assigned_audits.append(audit.number)
                    s.days_booked += audit.team_days[audit.primary_team] // max(1, audit.team_headcount[audit.primary_team])
                    if audit.number in s.preferences:
                        s.preference_satisfied = True
                    break
        if audit.assigned_tl is None and sam_pool:
            ranked = sorted(sam_pool, key=lambda s: score(s, audit)[0], reverse=True)
            tl = ranked[0]
            audit.assigned_tl = tl.name
            tl.assigned_audits.append(audit.number)
            tl.days_booked += audit.team_days[audit.primary_team] // max(1, audit.team_headcount[audit.primary_team])
            if audit.number in tl.preferences:
                tl.preference_satisfied = True

        if audit.assigned_tl is None:
            warnings.append(f"{audit.number}: no SAM available in primary team '{audit.primary_team}'")
            continue

        # Fill remaining slots per-team
        for team in TEAMS:
            need = audit.team_headcount[team]
            if team == audit.primary_team:
                need -= 1  # TL counted
            if need <= 0:
                continue
            per_person_days = audit.team_days[team] // max(1, audit.team_headcount[team])
            pool = [a for a in auditors.values()
                    if a.home_team == team and a.name != audit.assigned_tl
                    and audit.number not in a.assigned_audits
                    and availability_ratio(a, audit) >= 0.6]
            if len(pool) < need:
                warnings.append(f"{audit.number}: only {len(pool)} candidates in {team}, needed {need}")

            # Sort: prefer-unsatisfied-with-this-in-prefs first, then by score
            def sort_key(a: Auditor):
                base, _ = score(a, audit)
                pref_bonus = 0.5 if (audit.number in a.preferences and not a.preference_satisfied) else 0.0
                workload_penalty = -0.001 * a.days_booked
                return -(base + pref_bonus + workload_penalty)

            pool.sort(key=sort_key)
            picked = pool[:need]
            for p in picked:
                p.assigned_audits.append(audit.number)
                p.days_booked += per_person_days
                if audit.number in p.preferences:
                    p.preference_satisfied = True
                audit.assigned_members.append((p.name, p.home_team, per_person_days))

    # Capacity check
    available_days_per_person = working_days_between(date(SCHEDULE_YEAR, 1, 1),
                                                     date(SCHEDULE_YEAR, 12, 31))
    overloaded = [a.name for a in auditors.values()
                  if a.days_booked > available_days_per_person * 0.9]
    if overloaded:
        warnings.append(f"Overloaded auditors (>90% of year booked): {', '.join(overloaded)}")

    # Preference satisfaction
    unsatisfied = [a.name for a in auditors.values()
                   if a.preferences and not a.preference_satisfied]
    if unsatisfied:
        warnings.append(f"No preferred audit assigned to: {', '.join(unsatisfied)}")

    return warnings


# ----------------------------------------------------------------------------
# WRITERS
# ----------------------------------------------------------------------------

def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def write_grid(auditors: dict[str, Auditor], audits: list[Audit], path: Path) -> None:
    """Reproduce the planned_assignments.xlsx week-grid layout, one sheet per team."""
    wb = Workbook()
    wb.remove(wb.active)
    audit_by_num = {a.number: a for a in audits}

    # Build the 52-week column structure for SCHEDULE_YEAR
    first_monday = _monday_of(date(SCHEDULE_YEAR, 1, 1))
    if first_monday.year < SCHEDULE_YEAR:
        first_monday += timedelta(days=7)
    weeks = [first_monday + timedelta(weeks=i) for i in range(52)]
    months = []
    for w in weeks:
        m = w.strftime("%b-%y")
        months.append(m if (not months or months[-1] != m) else "")

    for team in TEAMS:
        ws = wb.create_sheet(team)
        ws["A1"] = "Auditor"
        ws["A1"].font = Font(bold=True)
        for i, m in enumerate(months, start=2):
            ws.cell(row=1, column=i, value=m).font = Font(bold=True)
        for i, w in enumerate(weeks, start=2):
            ws.cell(row=2, column=i, value=f"{w.day}/{w.strftime('%b')}")
        # auditors in this team
        team_auditors = [a for a in auditors.values() if a.home_team == team]
        team_auditors.sort(key=lambda a: (a.role != "SAM", a.role, a.name))
        for r, aud in enumerate(team_auditors, start=3):
            ws.cell(row=r, column=1, value=f"{aud.role}/{aud.name}")
            for audit_num in aud.assigned_audits:
                audit = audit_by_num[audit_num]
                for i, w in enumerate(weeks, start=2):
                    week_end = w + timedelta(days=4)
                    if audit.start_date <= week_end and audit.end_date >= w:
                        cur = ws.cell(row=r, column=i).value
                        ws.cell(row=r, column=i, value=audit.title if not cur else f"{cur}; {audit.title}")
        for col in range(1, len(weeks) + 2):
            ws.column_dimensions[get_column_letter(col)].width = 18 if col == 1 else 14
        ws.freeze_panes = "B3"

    wb.save(path)


def write_summary(audits: list[Audit], auditors: dict[str, Auditor], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    headers = ["Audit Number", "Title", "Primary Team", "Report Date", "Start", "End",
               "Total Days", "Split (ICS/T&A/DM)", "Headcount (ICS/T&A/DM)",
               "Team Lead", "Members", "Avg Skill Score", "Warnings"]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="305496")
        c.alignment = Alignment(horizontal="center")

    for r, a in enumerate(audits, start=2):
        scores = []
        if a.assigned_tl and a.assigned_tl in auditors:
            scores.append(score(auditors[a.assigned_tl], a)[1]["skill"])
        for m_name, _, _ in a.assigned_members:
            if m_name in auditors:
                scores.append(score(auditors[m_name], a)[1]["skill"])
        avg_skill = sum(scores) / len(scores) if scores else 0.0
        warns = []
        if not a.assigned_tl:
            warns.append("no TL")
        if len(a.assigned_members) + (1 if a.assigned_tl else 0) < MIN_TEAM_MEMBERS:
            warns.append("understaffed")
        ws.cell(row=r, column=1, value=a.number)
        ws.cell(row=r, column=2, value=a.title)
        ws.cell(row=r, column=3, value=a.primary_team)
        ws.cell(row=r, column=4, value=a.report_date.isoformat())
        ws.cell(row=r, column=5, value=a.start_date.isoformat())
        ws.cell(row=r, column=6, value=a.end_date.isoformat())
        ws.cell(row=r, column=7, value=a.total_days)
        ws.cell(row=r, column=8, value=f"{a.team_days.get('ICS',0)}/{a.team_days.get('T&A',0)}/{a.team_days.get('DM',0)}")
        ws.cell(row=r, column=9, value=f"{a.team_headcount.get('ICS',0)}/{a.team_headcount.get('T&A',0)}/{a.team_headcount.get('DM',0)}")
        ws.cell(row=r, column=10, value=a.assigned_tl or "—")
        ws.cell(row=r, column=11, value="; ".join(f"{n} ({t})" for n, t, _ in a.assigned_members))
        ws.cell(row=r, column=12, value=round(avg_skill, 2))
        ws.cell(row=r, column=13, value=", ".join(warns) if warns else "")

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 20
    ws.column_dimensions["B"].width = 38
    ws.column_dimensions["K"].width = 50
    ws.freeze_panes = "A2"
    wb.save(path)


def write_warnings(warnings: list[str], auditors: dict[str, Auditor], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Warnings"
    ws.cell(row=1, column=1, value="Type").font = Font(bold=True)
    ws.cell(row=1, column=2, value="Detail").font = Font(bold=True)
    for r, w in enumerate(warnings, start=2):
        ws.cell(row=r, column=1, value="SCHEDULER")
        ws.cell(row=r, column=2, value=w)

    ws2 = wb.create_sheet("Auditor Workload")
    ws2.append(["Auditor", "Role", "Team", "Audits Assigned", "Days Booked", "Preference Met"])
    for a in sorted(auditors.values(), key=lambda x: (x.home_team, x.role, x.name)):
        ws2.append([a.name, a.role, a.home_team, len(a.assigned_audits),
                    a.days_booked, "yes" if a.preference_satisfied else ("n/a" if not a.preferences else "no")])
    for col in range(1, 7):
        ws2.column_dimensions[get_column_letter(col)].width = 22
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 80
    wb.save(path)


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    print("Loading auditors...")
    auditors = load_auditors()
    print(f"  -> {len(auditors)} auditors across {len(TEAMS)} teams")

    print("Loading audits...")
    audits = load_audits()
    print(f"  -> {len(audits)} audits planned")

    print("Computing durations and team-day splits...")
    for a in audits:
        compute_duration(a)
        compute_split(a)

    print("Inferring required skills (Groq + cache)...")
    infer_skills_for_audits(audits)

    print("Solving assignments...")
    warnings = solve(auditors, audits)
    print(f"  -> {len(warnings)} warnings")

    print("Writing outputs...")
    write_grid(auditors, audits, OUTPUT_DIR / "assignments_grid.xlsx")
    write_summary(audits, auditors, OUTPUT_DIR / "assignments_summary.xlsx")
    write_warnings(warnings, auditors, OUTPUT_DIR / "warnings.xlsx")

    print("\nDone. Outputs in:", OUTPUT_DIR.resolve())
    for f in OUTPUT_DIR.iterdir():
        print(" -", f.name)


if __name__ == "__main__":
    main()
