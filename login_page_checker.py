"""
Login Page Checker v2
---------------------
Reads URLs from an Excel file and checks for login pages using a 3-step strategy:

  1. If URL already ends in /login (or similar), check it directly for username/password fields.
  2. If not, append /login and check there.
  3. If neither yields a login form, scrape the original page (incl. nav menus, footers,
     buttons) for any link or button labeled login / sign in / sign up / register / etc.
     If found, follow it and check that destination for username/password fields.

Uses Playwright (headless Chromium) so JS-rendered forms and nav menus are visible.

Usage:
    pip install pandas openpyxl playwright
    playwright install chromium
    python login_page_checker.py input.xlsx output.xlsx [--url-column URL] [--workers 5]
"""

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import urljoin, urlparse

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from playwright.async_api import async_playwright, Browser, TimeoutError as PWTimeout

# ---- Config ---------------------------------------------------------------

PAGE_TIMEOUT_MS = 15000
NAV_WAIT_MS = 2500  # extra wait after navigation for JS to render

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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class CheckResult:
    url: str
    has_login: bool = False
    login_url_found: str = ""
    detection_method: str = ""
    detection_reasons: str = ""
    status_code: str = ""
    error: str = ""


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


async def page_has_password_and_username(page) -> tuple[bool, list[str]]:
    """Look for a password field + paired username-like field. Returns (is_login, reasons)."""
    reasons = []

    pwd_count = await page.locator('input[type="password"]').count()
    if pwd_count == 0:
        return False, reasons
    reasons.append(f"{pwd_count} password field(s)")

    username_found = False
    candidates = await page.locator(
        'input[type="email"], input[type="tel"], input[type="text"], '
        'input:not([type]), input[type="number"]'
    ).all()

    for inp in candidates:
        try:
            attrs = await inp.evaluate(
                """el => ({
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    autocomplete: el.autocomplete || '',
                    type: el.type || ''
                })"""
            )
        except Exception:
            continue

        blob = " ".join(str(v) for v in attrs.values())
        if USERNAME_PATTERN.search(blob) or attrs.get("type") in ("email", "tel"):
            username_found = True
            label = attrs.get("name") or attrs.get("id") or attrs.get("placeholder") or attrs.get("type")
            reasons.append(f"username-like field: {label[:40]}")
            break

    if not username_found:
        try:
            title = (await page.title()) or ""
        except Exception:
            title = ""
        try:
            body_text = await page.evaluate(
                "() => document.body ? document.body.innerText.slice(0, 3000) : ''"
            )
        except Exception:
            body_text = ""
        text_blob = f"{title}\n{body_text}"
        if re.search(r"\b(sign[\s-]?in|log[\s-]?in)\b", text_blob, re.IGNORECASE):
            reasons.append("password field + login text on page")
            return True, reasons
        # Password field alone with no login context: likely a "change password" form. Reject.
        return False, []

    return True, reasons


async def find_login_link_on_page(page) -> Optional[str]:
    """Scrape every <a> and <button> (nav menus, footers, dropdowns) for a login link."""
    try:
        candidates = await page.evaluate(
            """() => {
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
                        href: '',
                        onclick: b.getAttribute('onclick') || ''
                    });
                });
                return out;
            }"""
        )
    except Exception:
        return None

    base_url = page.url

    # Pass 1: anchors with login-ish text AND login-ish href
    for c in candidates:
        if c["kind"] != "a" or not c["href"]:
            continue
        label = f"{c['text']} {c['aria']} {c['title']}"
        if LOGIN_LINK_TEXT.search(label) and LOGIN_HREF_PATTERN.search(c["href"]):
            return urljoin(base_url, c["href"])

    # Pass 2: anchors with login-ish text
    for c in candidates:
        if c["kind"] != "a" or not c["href"]:
            continue
        label = f"{c['text']} {c['aria']} {c['title']}"
        if LOGIN_LINK_TEXT.search(label):
            return urljoin(base_url, c["href"])

    # Pass 3: anchors with login-ish href only
    for c in candidates:
        if c["kind"] != "a" or not c["href"]:
            continue
        if c["href"].startswith(("javascript:", "mailto:", "#")):
            continue
        if LOGIN_HREF_PATTERN.search(c["href"]):
            return urljoin(base_url, c["href"])

    return None


async def goto_safe(page, url: str) -> tuple[bool, str, Optional[int]]:
    try:
        resp = await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        await page.wait_for_timeout(NAV_WAIT_MS)
        status = resp.status if resp else None
        return True, "", status
    except PWTimeout:
        return False, "timeout", None
    except Exception as e:
        return False, str(e)[:200], None


async def check_url(browser: Browser, raw_url: str) -> CheckResult:
    result = CheckResult(url=raw_url)
    url = normalize_url(raw_url)
    if not url:
        result.error = "empty url"
        return result

    context = await browser.new_context(
        user_agent=USER_AGENT,
        ignore_https_errors=True,
        viewport={"width": 1366, "height": 800},
    )
    page = await context.new_page()

    try:
        # Step 1: check the URL itself
        ok, err, status = await goto_safe(page, url)
        if status is not None:
            result.status_code = str(status)
        if not ok:
            result.error = err

        if ok:
            is_login, reasons = await page_has_password_and_username(page)
            if is_login:
                result.has_login = True
                result.login_url_found = page.url
                result.detection_method = "direct" if url_looks_like_login(url) else "original-url"
                result.detection_reasons = "; ".join(reasons)
                return result

        # Step 2: append /login if not already a login URL
        if not url_looks_like_login(url):
            appended = append_login(url)
            ok2, err2, status2 = await goto_safe(page, appended)
            if ok2:
                is_login, reasons = await page_has_password_and_username(page)
                if is_login:
                    result.has_login = True
                    result.login_url_found = page.url
                    result.detection_method = "appended"
                    result.detection_reasons = "; ".join(reasons)
                    if status2 is not None:
                        result.status_code = str(status2)
                    return result

        # Step 3: go back to original, scrape for login link
        ok3, err3, _ = await goto_safe(page, url)
        if not ok3:
            if not result.error:
                result.error = err3
            return result

        login_link = await find_login_link_on_page(page)
        if login_link:
            ok4, err4, status4 = await goto_safe(page, login_link)
            if ok4:
                is_login, reasons = await page_has_password_and_username(page)
                if is_login:
                    result.has_login = True
                    result.login_url_found = page.url
                    result.detection_method = "nav-link"
                    result.detection_reasons = "; ".join(reasons)
                    if status4 is not None:
                        result.status_code = str(status4)
                    return result
                else:
                    result.detection_method = "nav-link-no-form"
                    result.login_url_found = page.url
                    result.detection_reasons = "found login-style link but no password field at destination"

        if not result.detection_method:
            result.detection_method = "none"
        return result

    finally:
        await context.close()


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


async def run(urls: list[str], workers: int) -> list[CheckResult]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(workers)
        total = len(urls)
        done = 0
        lock = asyncio.Lock()

        async def worker(u: str):
            nonlocal done
            async with sem:
                res = await check_url(browser, u)
                async with lock:
                    done += 1
                    flag = "LOGIN" if res.has_login else "—"
                    print(f"[{done}/{total}] {flag:5s} ({res.detection_method or 'n/a'}) {u}")
                return res

        results = await asyncio.gather(*[worker(u) for u in urls])
        await browser.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Check URLs for login pages (Playwright).")
    parser.add_argument("input", help="Input .xlsx file with URLs")
    parser.add_argument("output", help="Output .xlsx file")
    parser.add_argument("--url-column", help="Name of URL column (auto-detected if omitted)")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent browsers (default 5)")
    args = parser.parse_args()

    df, url_col = read_urls(args.input, args.url_column)
    urls = df[url_col].dropna().astype(str).unique().tolist()
    print(f"Loaded {len(df)} rows. URL column: '{url_col}'. Checking {len(urls)} unique URLs.\n")

    start = time.time()
    results = asyncio.run(run(urls, args.workers))
    elapsed = time.time() - start

    found = sum(1 for r in results if r.has_login)
    print(f"\nDone in {elapsed:.1f}s. Login pages found on {found}/{len(urls)} URLs.")

    write_output(df, results, url_col, args.output)
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    sys.exit(main())
