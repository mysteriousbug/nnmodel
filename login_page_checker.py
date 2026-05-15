"""
Login Page Checker v3 (Selenium)
--------------------------------
Uses the Chrome or Edge browser already installed on the laptop.
No browser download required — Selenium Manager auto-fetches the matching driver.

Detection logic (3 steps):
  1. If URL already looks like a login page (ends in /login, /signin, etc.),
     check it directly for password + username-like fields.
  2. Else, append /login to the base domain and check that.
  3. Else, scrape the original page (incl. nav menus, footers, buttons rendered
     by JS) for any link/button labeled login/signin/signup/register/etc.,
     follow it, and check the destination.

Usage:
    pip install pandas openpyxl selenium
    python login_page_checker.py input.xlsx output.xlsx [--browser chrome|edge]
                                                        [--url-column URL]
                                                        [--workers 4]
                                                        [--headless / --no-headless]
"""

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import urljoin, urlparse

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
)

# ---- Config ---------------------------------------------------------------

PAGE_LOAD_TIMEOUT = 20  # seconds
SCRIPT_TIMEOUT = 10
POST_LOAD_WAIT = 2.0    # extra seconds for JS to render after page load

LOGIN_PATH_PATTERN = re.compile(
    r"/(login|signin|sign-in|log-in|signup|sign-up|register|auth|sso|account/login)/?$",
    re.IGNORECASE,
)

LOGIN_LINK_TEXT = re.compile(
    r"\b(log[\s-]?in|sign[\s-]?in|sign[\s-]?up|register|create\s+account|"
    r"my\s+account|member\s+login|customer\s+login|join\s+now)\b",
    re.IGNORECASE,
)

LOGIN_HREF_PATTERN = re.compile(
    r"(login|signin|sign-in|log-in|signup|sign-up|register|auth|sso)",
    re.IGNORECASE,
)

USERNAME_PATTERN = re.compile(
    r"(user(name)?|email|e-mail|mobile|phone|login|userid|user_id|account)",
    re.IGNORECASE,
)


@dataclass
class CheckResult:
    url: str
    has_login: bool = False
    login_url_found: str = ""
    detection_method: str = ""
    detection_reasons: str = ""
    error: str = ""


# ---- URL helpers ----------------------------------------------------------

def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def url_looks_like_login(url: str) -> bool:
    path = urlparse(url).path or ""
    return bool(LOGIN_PATH_PATTERN.search(path))


def append_login(url: str) -> str:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return base.rstrip("/") + "/login"


# ---- Driver factory -------------------------------------------------------

def make_driver(browser: str, headless: bool):
    """
    Build a Selenium driver using the locally installed Chrome or Edge.
    Selenium Manager (built into Selenium 4.6+) auto-downloads the driver.
    If your network blocks even that, the script falls back to assuming the
    driver is on PATH.
    """
    if browser == "chrome":
        opts = webdriver.ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--ignore-certificate-errors")
        opts.add_argument("--window-size=1366,800")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        driver = webdriver.Chrome(options=opts)
    elif browser == "edge":
        opts = webdriver.EdgeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--ignore-certificate-errors")
        opts.add_argument("--window-size=1366,800")
        driver = webdriver.Edge(options=opts)
    else:
        raise ValueError(f"Unsupported browser: {browser}")

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    return driver


# ---- Page inspection ------------------------------------------------------

def page_has_password_and_username(driver) -> tuple[bool, list[str]]:
    """Look for password + paired username-like field. Returns (is_login, reasons)."""
    reasons = []

    try:
        pwd_fields = driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
    except WebDriverException:
        return False, reasons

    if not pwd_fields:
        return False, reasons
    reasons.append(f"{len(pwd_fields)} password field(s)")

    # Find username-like field. Accept type=email, tel, text/number with username-y attrs.
    username_found = False
    try:
        candidates = driver.find_elements(
            By.CSS_SELECTOR,
            'input[type="email"], input[type="tel"], input[type="text"], '
            'input[type="number"], input:not([type])',
        )
    except WebDriverException:
        candidates = []

    for inp in candidates:
        try:
            attrs = driver.execute_script(
                """
                const el = arguments[0];
                return {
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    autocomplete: el.autocomplete || '',
                    type: el.type || ''
                };
                """,
                inp,
            )
        except WebDriverException:
            continue

        blob = " ".join(str(v) for v in attrs.values())
        if USERNAME_PATTERN.search(blob) or attrs.get("type") in ("email", "tel"):
            username_found = True
            label = (
                attrs.get("name")
                or attrs.get("id")
                or attrs.get("placeholder")
                or attrs.get("type")
            )
            reasons.append(f"username-like field: {str(label)[:40]}")
            break

    if not username_found:
        # Password alone — check page title/text for login keywords as a tiebreaker.
        try:
            title = driver.title or ""
        except WebDriverException:
            title = ""
        try:
            body_text = driver.execute_script(
                "return document.body ? document.body.innerText.slice(0, 3000) : '';"
            ) or ""
        except WebDriverException:
            body_text = ""

        if re.search(r"\b(sign[\s-]?in|log[\s-]?in)\b", f"{title}\n{body_text}", re.IGNORECASE):
            reasons.append("password field + login text on page")
            return True, reasons
        # Likely a change-password form on a settings page. Reject.
        return False, []

    return True, reasons


def find_login_link_on_page(driver) -> Optional[str]:
    """Scrape all <a> and <button> for a login-like link. Returns absolute URL or None."""
    try:
        candidates = driver.execute_script(
            """
            const out = [];
            document.querySelectorAll('a').forEach(a => {
                out.push({
                    kind: 'a',
                    text: (a.innerText || a.textContent || '').trim(),
                    aria: a.getAttribute('aria-label') || '',
                    title: a.getAttribute('title') || '',
                    href: a.href || ''
                });
            });
            document.querySelectorAll('button, [role="button"]').forEach(b => {
                out.push({
                    kind: 'btn',
                    text: (b.innerText || b.textContent || '').trim(),
                    aria: b.getAttribute('aria-label') || '',
                    title: b.getAttribute('title') || '',
                    href: ''
                });
            });
            return out;
            """
        ) or []
    except WebDriverException:
        return None

    base_url = driver.current_url

    # Pass 1: login-ish text AND login-ish href (highest confidence)
    for c in candidates:
        if c["kind"] != "a" or not c["href"]:
            continue
        label = f"{c['text']} {c['aria']} {c['title']}"
        if LOGIN_LINK_TEXT.search(label) and LOGIN_HREF_PATTERN.search(c["href"]):
            return urljoin(base_url, c["href"])

    # Pass 2: login-ish text
    for c in candidates:
        if c["kind"] != "a" or not c["href"]:
            continue
        label = f"{c['text']} {c['aria']} {c['title']}"
        if LOGIN_LINK_TEXT.search(label):
            return urljoin(base_url, c["href"])

    # Pass 3: login-ish href
    for c in candidates:
        if c["kind"] != "a" or not c["href"]:
            continue
        if c["href"].startswith(("javascript:", "mailto:", "#")):
            continue
        if LOGIN_HREF_PATTERN.search(c["href"]):
            return urljoin(base_url, c["href"])

    return None


def goto_safe(driver, url: str) -> tuple[bool, str]:
    try:
        driver.get(url)
        time.sleep(POST_LOAD_WAIT)
        return True, ""
    except TimeoutException:
        return False, "timeout"
    except WebDriverException as e:
        return False, str(e).splitlines()[0][:200]


# ---- Core check -----------------------------------------------------------

def check_url(driver, raw_url: str) -> CheckResult:
    result = CheckResult(url=raw_url)
    url = normalize_url(raw_url)
    if not url:
        result.error = "empty url"
        return result

    # Step 1: check URL as-is
    ok, err = goto_safe(driver, url)
    if not ok:
        result.error = err
    else:
        is_login, reasons = page_has_password_and_username(driver)
        if is_login:
            result.has_login = True
            result.login_url_found = driver.current_url
            result.detection_method = "direct" if url_looks_like_login(url) else "original-url"
            result.detection_reasons = "; ".join(reasons)
            return result

    # Step 2: append /login if not already a login URL
    if not url_looks_like_login(url):
        appended = append_login(url)
        ok2, err2 = goto_safe(driver, appended)
        if ok2:
            is_login, reasons = page_has_password_and_username(driver)
            if is_login:
                result.has_login = True
                result.login_url_found = driver.current_url
                result.detection_method = "appended"
                result.detection_reasons = "; ".join(reasons)
                return result

    # Step 3: scrape original page for a login link
    ok3, err3 = goto_safe(driver, url)
    if not ok3:
        if not result.error:
            result.error = err3
        result.detection_method = "none"
        return result

    login_link = find_login_link_on_page(driver)
    if login_link:
        ok4, err4 = goto_safe(driver, login_link)
        if ok4:
            is_login, reasons = page_has_password_and_username(driver)
            if is_login:
                result.has_login = True
                result.login_url_found = driver.current_url
                result.detection_method = "nav-link"
                result.detection_reasons = "; ".join(reasons)
                return result
            else:
                result.detection_method = "nav-link-no-form"
                result.login_url_found = driver.current_url
                result.detection_reasons = "found login-style link but no password field at destination"
                return result

    if not result.detection_method:
        result.detection_method = "none"
    return result


# ---- Excel I/O ------------------------------------------------------------

def read_urls(path: str, url_column: Optional[str]) -> tuple[pd.DataFrame, str]:
    df = pd.read_excel(path)
    if url_column and url_column in df.columns:
        col = url_column
    else:
        matches = [c for c in df.columns if "url" in str(c).lower()]
        col = matches[0] if matches else df.columns[0]
    return df, col


def write_output(df: pd.DataFrame, results: list[CheckResult], url_col: str, out_path: str):
    res_df = pd.DataFrame([asdict(r) for r in results]).rename(columns={"url": url_col})
    merged = df.merge(res_df, on=url_col, how="left", suffixes=("", "_check"))
    merged.to_excel(out_path, index=False)

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

    for col_cells in ws.columns:
        length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(length + 2, 60)

    wb.save(out_path)


# ---- Orchestration --------------------------------------------------------

def worker_thread(urls: list[str], browser: str, headless: bool, progress: dict, lock):
    """One driver per worker thread. Each thread processes its share of URLs."""
    driver = None
    results = []
    try:
        driver = make_driver(browser, headless)
        for u in urls:
            res = check_url(driver, u)
            results.append(res)
            with lock:
                progress["done"] += 1
                done = progress["done"]
                total = progress["total"]
                flag = "LOGIN" if res.has_login else "—"
                method = res.detection_method or "n/a"
                print(f"[{done}/{total}] {flag:5s} ({method}) {u}")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    return results


def chunk(lst, n):
    """Split lst into n roughly-equal chunks."""
    if n <= 0:
        n = 1
    k, m = divmod(len(lst), n)
    return [lst[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]


def main():
    parser = argparse.ArgumentParser(description="Check URLs for login pages using Selenium.")
    parser.add_argument("input", help="Input .xlsx file with URLs")
    parser.add_argument("output", help="Output .xlsx file")
    parser.add_argument("--url-column", help="Name of URL column (auto-detected if omitted)")
    parser.add_argument("--browser", choices=["chrome", "edge"], default="chrome",
                        help="Which installed browser to use (default chrome)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Concurrent browser instances (default 4)")
    parser.add_argument("--headless", dest="headless", action="store_true", default=True,
                        help="Run headless (default)")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Show browser windows (useful for debugging)")
    args = parser.parse_args()

    df, url_col = read_urls(args.input, args.url_column)
    urls = df[url_col].dropna().astype(str).unique().tolist()
    print(f"Loaded {len(df)} rows. URL column: '{url_col}'. Checking {len(urls)} unique URLs.")
    print(f"Browser: {args.browser} | Headless: {args.headless} | Workers: {args.workers}\n")

    progress = {"done": 0, "total": len(urls)}
    import threading
    lock = threading.Lock()

    start = time.time()
    chunks = [c for c in chunk(urls, args.workers) if c]
    all_results: list[CheckResult] = []

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = [
            pool.submit(worker_thread, c, args.browser, args.headless, progress, lock)
            for c in chunks
        ]
        for fut in as_completed(futures):
            try:
                all_results.extend(fut.result())
            except Exception as e:
                print(f"Worker failed: {e}")

    elapsed = time.time() - start
    found = sum(1 for r in all_results if r.has_login)
    print(f"\nDone in {elapsed:.1f}s. Login pages found on {found}/{len(urls)} URLs.")

    write_output(df, all_results, url_col, args.output)
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    sys.exit(main())
