import logging
import os

import config

log = logging.getLogger(__name__)

_mx_cache = {}


def validate_email(email):
    """Check if an extracted string is a plausible real email address."""
    email = email.lower().strip()

    if not config.EMAIL_REGEX.fullmatch(email):
        return False

    local, domain = email.rsplit('@', 1)

    # Reject excluded domains
    if domain in config.EXCLUDED_EMAIL_DOMAINS:
        return False

    # Reject excluded prefixes
    if local in config.EXCLUDED_EMAIL_PREFIXES:
        return False

    # Reject file extensions that look like emails
    for ext in config.FALSE_POSITIVE_EXTENSIONS:
        if ext in email:
            return False

    # Reject very long or very short
    if len(local) < 2 or len(local) > 64 or len(domain) < 4:
        return False

    # Reject if domain has no dot (not a real domain)
    if '.' not in domain:
        return False

    return True


def normalize_email(email):
    return email.lower().strip()


def verify_mx(domain):
    """Optional: verify domain has MX records. Results are cached."""
    if domain in _mx_cache:
        return _mx_cache[domain]

    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
        has_mx = len(answers) > 0
    except Exception:
        has_mx = False

    _mx_cache[domain] = has_mx
    return has_mx
