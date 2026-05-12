"""
Login Page Checker
------------------
Reads URLs from an Excel file, checks each URL (and common login paths)
for the presence of a login page, and writes a flagged Excel output.

Usage:
    python login_page_checker.py input.xlsx output.xlsx [--url-column URL]

Detection logic:
    1. Fetches the original URL.
    2. Fetches common login paths on the same domain (/login, /signin, etc.).
    3. Flags a page as a "login page" if it contains login-form indicators:
       - <input type="password">
       - login/signin form action attributes
       - keywords like "sign in", "log in", "username", "password" near a form
"""

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---- Config ---------------------------------------------------------------

COMMON_LOGIN_PATHS = [
    "/login", "/signin", "/sign-in", "/log-in",
    "/account/login", "/user/login", "/users/sign_in",
    "/auth/login", "/auth/signin", "/wp-login.php",
    "/admin", "/admin/login", "/portal/login",
]

LOGIN_KEYWORDS = re.compile(
    r"\b(sign[\s-]?in|log[\s-]?in|username|user\s*id|email\s*address|password)\b",
    re.IGNORECASE,
)

REQUEST_TIMEOUT = 10  # seconds
MAX_WORKERS = 10
USER_AGENT = (
    "Mozilla/5.0 (compatible; LoginPageChecker/1.0; +https://example.local)"
)

# ---- HTTP session with retries -------------------------------------------

def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


# ---- Detection -----------------------------------------------------------

def page_has_login(html: str) -> tuple[bool, list[str]]:
    """Return (is_login_page, reasons)."""
    reasons = []
    if not html:
        return False, reasons

    soup = BeautifulSoup(html, "html.parser")

    # 1. Password field is the strongest signal.
    if soup.find("input", {"type": "password"}):
        reasons.append("password field")

    # 2. Form action that looks like login.
    for form in soup.find_all("form"):
        action = (form.get("action") or "").lower()
        form_id = (form.get("id") or "").lower()
        form_class = " ".join(form.get("class") or []).lower()
        if any(k in action for k in ("login", "signin", "sign-in", "auth")):
            reasons.append(f"form action: {action}")
            break
        if any(k in (form_id + " " + form_class) for k in ("login", "signin")):
            reasons.append(f"form id/class: {form_id or form_class}")
            break

    # 3. Page text mentions login + has any form.
    if not reasons and soup.find("form"):
        text = soup.get_text(" ", strip=True)[:5000]
        if LOGIN_KEYWORDS.search(text):
            reasons.append("login keywords near form")

    # 4. <title> says login/sign in
    title_tag = soup.find("title")
    if title_tag and LOGIN_KEYWORDS.search(title_tag.get_text() or ""):
        if "login keywords near form" not in reasons:
            reasons.append(f"title: {title_tag.get_text(strip=True)[:60]}")

    return bool(reasons), reasons


def fetch(session: requests.Session, url: str) -> tuple[int | None, str, str | None]:
    """Return (status_code, html, error)."""
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return r.status_code, r.text, None
    except requests.RequestException as e:
        return None, "", str(e)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def check_url(session: requests.Session, raw_url: str) -> dict:
    """Check the URL itself + common login paths."""
    result = {
        "url": raw_url,
        "has_login": False,
        "login_url_found": "",
        "status_code": "",
        "detection_reasons": "",
        "error": "",
    }

    url = normalize_url(raw_url)
    if not url:
        result["error"] = "empty url"
        return result

    # 1. Check the URL as-is.
    status, html, err = fetch(session, url)
    if err:
        result["error"] = err
    result["status_code"] = status if status is not None else ""

    if html:
        is_login, reasons = page_has_login(html)
        if is_login:
            result["has_login"] = True
            result["login_url_found"] = url
            result["detection_reasons"] = "; ".join(reasons)
            return result

    # 2. Check common login paths on the same origin.
    parsed = urlparse(url)
    if not parsed.netloc:
        return result
    base = f"{parsed.scheme}://{parsed.netloc}"

    for path in COMMON_LOGIN_PATHS:
        candidate = urljoin(base, path)
        c_status, c_html, c_err = fetch(session, candidate)
        if c_status and 200 <= c_status < 400 and c_html:
            is_login, reasons = page_has_login(c_html)
            if is_login:
                result["has_login"] = True
                result["login_url_found"] = candidate
                result["status_code"] = c_status
                result["detection_reasons"] = "; ".join(reasons)
                return result

    return result


# ---- Excel I/O ------------------------------------------------------------

def read_urls(path: str, url_column: str | None) -> tuple[pd.DataFrame, str]:
    df = pd.read_excel(path)
    if url_column and url_column in df.columns:
        col = url_column
    else:
        # auto-detect: first column containing "url" (case-insensitive), else first column
        matches = [c for c in df.columns if "url" in str(c).lower()]
        col = matches[0] if matches else df.columns[0]
    return df, col


def write_output(df: pd.DataFrame, results: list[dict], url_col: str, out_path: str):
    res_df = pd.DataFrame(results).rename(columns={"url": url_col})
    # Merge results back onto original df on URL.
    merged = df.merge(res_df, on=url_col, how="left", suffixes=("", "_check"))

    merged.to_excel(out_path, index=False)

    # Highlight rows where has_login is True.
    wb = load_workbook(out_path)
    ws = wb.active

    headers = [c.value for c in ws[1]]
    try:
        flag_col_idx = headers.index("has_login") + 1
    except ValueError:
        wb.save(out_path)
        return

    yellow = PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")
    bold = Font(bold=True)
    for cell in ws[1]:
        cell.font = bold

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        flag_cell = row[flag_col_idx - 1]
        if flag_cell.value is True or str(flag_cell.value).lower() == "true":
            for c in row:
                c.fill = yellow

    # Auto-ish column widths
    for col_cells in ws.columns:
        length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(length + 2, 60)

    wb.save(out_path)


# ---- Main -----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Check URLs for login pages.")
    parser.add_argument("input", help="Input .xlsx file with URLs")
    parser.add_argument("output", help="Output .xlsx file")
    parser.add_argument("--url-column", help="Name of the URL column (auto-detected if omitted)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    df, url_col = read_urls(args.input, args.url_column)
    print(f"Loaded {len(df)} rows. Using URL column: '{url_col}'")

    urls = df[url_col].dropna().astype(str).unique().tolist()
    session = make_session()

    results: list[dict] = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check_url, session, u): u for u in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            results.append(res)
            flag = "LOGIN" if res["has_login"] else "—"
            print(f"[{i}/{len(urls)}] {flag:5s} {res['url']}")

    elapsed = time.time() - start
    found = sum(1 for r in results if r["has_login"])
    print(f"\nDone in {elapsed:.1f}s. Login pages found on {found}/{len(urls)} URLs.")

    write_output(df, results, url_col, args.output)
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    sys.exit(main())
