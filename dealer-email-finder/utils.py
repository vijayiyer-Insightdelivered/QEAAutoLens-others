import logging
import random
import re
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter, Retry

import config


def create_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': random.choice(config.USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.9',
    })
    return session


class RateLimiter:
    def __init__(self):
        self._last_request = {}

    def wait(self, group, delay, jitter=0):
        now = time.time()
        last = self._last_request.get(group, 0)
        elapsed = now - last
        total_delay = delay + random.uniform(0, jitter)
        if elapsed < total_delay:
            time.sleep(total_delay - elapsed)
        self._last_request[group] = time.time()


def setup_logging(verbose=False, log_path=None):
    log_path = log_path or config.DEFAULT_LOG_PATH
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s', datefmt='%H:%M:%S')

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(formatter)
    root.addHandler(sh)


_STRIP_SUFFIXES = re.compile(r'\b(ltd|limited|plc|llp|inc|corp|co)\b', re.IGNORECASE)
_MULTI_SPACE = re.compile(r'\s+')

def clean_company_name(name):
    name = _STRIP_SUFFIXES.sub('', name)
    name = re.sub(r'[^\w\s-]', '', name)
    name = _MULTI_SPACE.sub(' ', name).strip()
    return name


def name_to_slugs(name):
    cleaned = clean_company_name(name).lower()
    words = cleaned.split()
    if not words:
        return []
    joined = ''.join(words)
    hyphenated = '-'.join(words)
    slugs = [joined]
    if hyphenated != joined:
        slugs.append(hyphenated)
    return slugs


def extract_postcode_area(postcode):
    if not postcode:
        return ''
    match = re.match(r'^([A-Z]{1,2}\d{1,2}[A-Z]?)', postcode.strip().upper())
    return match.group(1) if match else postcode.split()[0] if postcode.strip() else ''


def get_domain(url):
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().lstrip('www.')
    except Exception:
        return ''


def is_aggregator(url):
    domain = get_domain(url)
    return any(agg in domain for agg in config.AGGREGATOR_DOMAINS)
