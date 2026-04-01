import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import config
from utils import RateLimiter, clean_company_name, extract_postcode_area, is_aggregator, name_to_slugs

log = logging.getLogger(__name__)

SEARCH_ENGINE_DOMAINS = {'bing.com', 'www.bing.com', 'google.com', 'www.google.com',
                         'duckduckgo.com', 'www.duckduckgo.com', 'yahoo.com', 'www.yahoo.com'}


def search_for_website(company_name, postcode, session, rate_limiter, search_engine='duckduckgo', industry=''):
    """Search for a company's website. Returns the best-matching URL or None."""
    cleaned = clean_company_name(company_name)
    area = extract_postcode_area(postcode)
    industry = industry.strip() if industry else ''

    # Stage 0: Try direct domain probe first (most reliable)
    slugs = name_to_slugs(company_name)
    direct = _try_direct_domains(slugs, session, rate_limiter)
    if direct:
        log.info(f"Found website for '{company_name}': {direct} (direct domain probe)")
        return direct

    # Build search queries — most specific first
    if industry:
        queries = [
            f'"{cleaned}" {industry} {area}',
            f'"{cleaned}" {industry}',
            f'{cleaned} {industry}',
        ]
    else:
        queries = [
            f'"{cleaned}" {area}' if area else f'"{cleaned}"',
            f'"{cleaned}"',
            f'{cleaned}',
        ]

    for query in queries:
        # Collect all valid candidate URLs from search results
        candidates = _search_duckduckgo_all(query, rate_limiter)

        if not candidates:
            candidates = _search_bing_all(query, session, rate_limiter)

        if not candidates:
            continue

        # Score and rank candidates by relevance to company name
        best = _pick_best_result(candidates, slugs, cleaned)
        if best:
            log.info(f"Found website for '{company_name}': {best} (query: {query})")
            return best

    log.debug(f"No website found for '{company_name}'")
    return None


def _pick_best_result(candidates, slugs, cleaned_name):
    """Score candidates by how well their domain matches the company name."""
    scored = []
    name_words = set(cleaned_name.lower().split())

    for url in candidates:
        domain = urlparse(url).netloc.lower().lstrip('www.')
        domain_base = domain.split('.')[0]  # e.g. 'insightdelivered' from 'insightdelivered.com'
        score = 0

        # Exact slug match in domain — very strong signal
        for slug in slugs:
            if slug in domain_base:
                score += 100
            elif slug in domain:
                score += 80

        # Partial word matches
        for word in name_words:
            if len(word) >= 3 and word in domain_base:
                score += 20

        # Penalize very generic domains (long paths of unrelated sites)
        if score == 0:
            score = 1  # still valid, just low priority

        scored.append((score, url))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    if scored:
        best_score, best_url = scored[0]
        log.debug(f"Best result: {best_url} (score={best_score}), candidates: {[(s, u) for s, u in scored[:5]]}")
        return _normalize_url(best_url)

    return None


def _try_direct_domains(slugs, session, rate_limiter):
    """Try the company name as a domain directly (e.g. insightdelivered.com)."""
    for slug in slugs:
        for suffix in ['.com', '.co.uk', '.uk']:
            domain = f"{slug}{suffix}"
            url = f"https://{domain}"
            try:
                rate_limiter.wait('domain', config.RATE_LIMIT_DOMAIN_PROBE, config.JITTER_DOMAIN_PROBE)
                resp = session.head(url, timeout=8, allow_redirects=True)
                if resp.status_code in (200, 403):  # 403 = site exists but blocks HEAD
                    log.debug(f"Direct domain hit: {domain} (status={resp.status_code})")
                    return url
            except Exception:
                continue
    return None


def _is_valid_result(url):
    if not url or not url.startswith('http'):
        return False
    domain = urlparse(url).netloc.lower()
    if domain in SEARCH_ENGINE_DOMAINS:
        return False
    return not is_aggregator(url)


def _search_duckduckgo_all(query, rate_limiter):
    """Return all valid candidate URLs from DuckDuckGo."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        rate_limiter.wait('search', config.RATE_LIMIT_SEARCH, config.JITTER_SEARCH)
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=10))

        candidates = []
        for r in results:
            href = r.get('href', '') or r.get('link', '') or r.get('url', '')
            if _is_valid_result(href):
                candidates.append(href)
        return candidates
    except Exception as e:
        log.warning(f"DuckDuckGo search failed: {e}")
    return []


def _search_bing_all(query, session, rate_limiter):
    """Return all valid candidate URLs from Bing."""
    try:
        rate_limiter.wait('search', config.RATE_LIMIT_SEARCH, config.JITTER_SEARCH)
        resp = session.get(
            'https://www.bing.com/search',
            params={'q': query},
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'lxml')

        candidates = []
        seen = set()

        # Try multiple selectors
        for selector in ['li.b_algo h2 a', 'li.b_algo a[href]', '#b_results li.b_algo a[href]']:
            for a in soup.select(selector):
                href = a.get('href', '')
                if _is_valid_result(href) and href not in seen:
                    candidates.append(href)
                    seen.add(href)

        return candidates
    except Exception as e:
        log.warning(f"Bing search failed: {e}")
    return []


def _normalize_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"
