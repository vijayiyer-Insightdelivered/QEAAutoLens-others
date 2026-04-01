import logging

import config
from utils import RateLimiter, name_to_slugs

log = logging.getLogger(__name__)


def guess_domain(company_name, session, rate_limiter):
    """Try common domain patterns to find a dealer's website."""
    slugs = name_to_slugs(company_name)
    if not slugs:
        return None

    attempts = 0
    for slug in slugs:
        for modifier in config.DOMAIN_MODIFIERS:
            for suffix in config.DOMAIN_SUFFIXES:
                if attempts >= config.MAX_DOMAIN_GUESSES:
                    return None

                if modifier:
                    domain = f"{slug}{modifier}{suffix}"
                else:
                    domain = f"{slug}{suffix}"

                url = f"https://{domain}"
                attempts += 1

                try:
                    rate_limiter.wait('domain', config.RATE_LIMIT_DOMAIN_PROBE, config.JITTER_DOMAIN_PROBE)
                    resp = session.head(url, timeout=8, allow_redirects=True)
                    if resp.status_code == 200:
                        final_url = resp.url if hasattr(resp, 'url') else url
                        log.info(f"Domain guess hit: {domain} -> {final_url}")
                        return f"https://{domain}"
                except Exception:
                    continue

    return None
