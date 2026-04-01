import json
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from email_validator import normalize_email, validate_email
from utils import RateLimiter

log = logging.getLogger(__name__)

# Shared Playwright browser instance (lazy-initialized)
_browser = None
_playwright = None


def _get_browser():
    """Lazy-initialize a shared Playwright browser."""
    global _browser, _playwright
    if _browser is None:
        try:
            from playwright.sync_api import sync_playwright
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=True)
            log.info("Playwright browser initialized")
        except Exception as e:
            log.warning(f"Playwright not available, using requests only: {e}")
    return _browser


def extract_emails_from_website(base_url, session, rate_limiter, verify_mx=False):
    """Scrape a website for email addresses. Uses requests first, Playwright as fallback."""
    all_emails = {}

    # Try requests first (fast)
    blocked = _scrape_page_requests(base_url, 'homepage', session, rate_limiter, all_emails)

    if not blocked:
        # Requests worked — continue with requests for other pages
        for path in config.CONTACT_PATHS:
            page_url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
            _scrape_page_requests(page_url, path.strip('/'), session, rate_limiter, all_emails)
    else:
        # Requests blocked (403/cloudflare) — use Playwright for all pages
        log.info(f"Requests blocked for {base_url}, switching to Playwright")
        urls_to_scrape = [base_url] + [
            urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
            for path in config.CONTACT_PATHS
        ]
        _scrape_with_playwright(urls_to_scrape, all_emails)

    # If requests found nothing and Playwright wasn't tried yet, try Playwright on key pages
    if not all_emails and not blocked:
        log.debug(f"No emails via requests for {base_url}, trying Playwright")
        urls_to_scrape = [base_url] + [
            urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
            for path in ['/contact', '/contact-us']
        ]
        _scrape_with_playwright(urls_to_scrape, all_emails)

    # Optional MX verification
    if verify_mx and all_emails:
        from email_validator import verify_mx as check_mx
        verified = {}
        for email, source in all_emails.items():
            domain = email.rsplit('@', 1)[1]
            if check_mx(domain):
                verified[email] = source
        return verified

    return all_emails


def _scrape_page_requests(url, source_label, session, rate_limiter, results):
    """Scrape a page with requests. Returns True if blocked (403/captcha)."""
    try:
        rate_limiter.wait('website', config.RATE_LIMIT_WEBSITE, config.JITTER_WEBSITE)
        import requests as _req
        resp = _req.get(url, timeout=10, headers=session.headers, allow_redirects=True)

        if resp.status_code in (403, 503):
            return True  # blocked
        if resp.status_code != 200:
            return False

        _extract_emails_from_html(resp.text, source_label, results)
        return False

    except Exception as e:
        log.debug(f"Failed to scrape {url}: {e}")
        return False


def _scrape_with_playwright(urls, results):
    """Scrape multiple URLs using a headless browser."""
    browser = _get_browser()
    if not browser:
        return

    try:
        page = browser.new_page()
        page.set_default_timeout(12000)

        for url in urls:
            try:
                resp = page.goto(url, wait_until='domcontentloaded', timeout=12000)
                if resp and resp.status == 200:
                    # Wait briefly for JS to render
                    page.wait_for_timeout(1500)
                    html = page.content()
                    # Derive source label from path
                    from urllib.parse import urlparse
                    path = urlparse(url).path.strip('/') or 'homepage'
                    _extract_emails_from_html(html, f"{path}/browser", results)
            except Exception as e:
                log.debug(f"Playwright failed for {url}: {e}")

        page.close()
    except Exception as e:
        log.warning(f"Playwright session error: {e}")


def _extract_emails_from_html(html, source_label, results):
    """Extract emails from raw HTML string."""
    soup = BeautifulSoup(html, 'lxml')

    # Extract mailto: links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('mailto:'):
            email = href.replace('mailto:', '').split('?')[0].strip()
            email = normalize_email(email)
            if validate_email(email) and email not in results:
                results[email] = source_label

    # Regex scan full HTML
    for match in config.EMAIL_REGEX.findall(html):
        email = normalize_email(match)
        if validate_email(email) and email not in results:
            results[email] = source_label

    # Check JSON-LD structured data
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
            _extract_from_jsonld(data, source_label + '/jsonld', results)
        except (json.JSONDecodeError, TypeError):
            pass


def _extract_from_jsonld(data, source_label, results):
    if isinstance(data, dict):
        for key in ('email', 'contactPoint'):
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    email = normalize_email(val.replace('mailto:', ''))
                    if validate_email(email) and email not in results:
                        results[email] = source_label
                elif isinstance(val, dict) and 'email' in val:
                    email = normalize_email(val['email'].replace('mailto:', ''))
                    if validate_email(email) and email not in results:
                        results[email] = source_label
                elif isinstance(val, list):
                    for item in val:
                        _extract_from_jsonld(item, source_label, results)
    elif isinstance(data, list):
        for item in data:
            _extract_from_jsonld(item, source_label, results)
