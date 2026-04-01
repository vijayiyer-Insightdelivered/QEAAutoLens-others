import logging

from bs4 import BeautifulSoup

import config
from utils import RateLimiter

log = logging.getLogger(__name__)


def scrape_companies_house(url, session, rate_limiter):
    """Scrape Companies House page for company status and officer names."""
    result = {
        'company_status': None,
        'officers': [],
        'sic_codes': [],
    }

    try:
        rate_limiter.wait('ch', config.RATE_LIMIT_CH, config.JITTER_CH)
        resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        # Extract company status
        status_el = soup.find('dd', {'id': 'company-status'})
        if status_el:
            result['company_status'] = status_el.get_text(strip=True)

        # Extract SIC codes
        sic_list = soup.find('ul', {'id': 'sic-list'})
        if sic_list:
            result['sic_codes'] = [li.get_text(strip=True) for li in sic_list.find_all('li')]

        # Scrape officers page
        officers_url = url.rstrip('/') + '/officers'
        rate_limiter.wait('ch', config.RATE_LIMIT_CH, config.JITTER_CH)
        resp2 = session.get(officers_url, timeout=config.REQUEST_TIMEOUT)
        if resp2.status_code == 200:
            soup2 = BeautifulSoup(resp2.text, 'lxml')
            officer_links = soup2.select('.officer-name a, .appointment-1 a, [data-event="officer-name"]')
            if not officer_links:
                # Fallback: look for officer name patterns in appointment lists
                appointment_divs = soup2.select('.appointment-1, .officer-status')
                for div in appointment_divs:
                    name_el = div.find(['a', 'span', 'h2'])
                    if name_el:
                        name = name_el.get_text(strip=True)
                        if name and len(name) > 2 and name not in result['officers']:
                            result['officers'].append(name)

            for link in officer_links:
                name = link.get_text(strip=True)
                if name and name not in result['officers']:
                    result['officers'].append(name)

    except Exception as e:
        log.warning(f"CH scrape failed for {url}: {e}")

    return result
