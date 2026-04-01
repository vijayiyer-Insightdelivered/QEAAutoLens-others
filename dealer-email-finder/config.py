import re

# Rate limits (seconds between requests per domain group)
RATE_LIMIT_CH = 2.0
RATE_LIMIT_SEARCH = 3.0
RATE_LIMIT_WEBSITE = 1.0
RATE_LIMIT_DOMAIN_PROBE = 0.5

# Jitter range (added randomly to rate limits)
JITTER_CH = 1.0
JITTER_SEARCH = 2.0
JITTER_WEBSITE = 0.5
JITTER_DOMAIN_PROBE = 0.5

REQUEST_TIMEOUT = 15

# Email extraction
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

EXCLUDED_EMAIL_DOMAINS = {
    'example.com', 'example.org', 'test.com',
    'sentry.io', 'wixpress.com', 'squarespace.com', 'cloudflare.com',
    'googleapis.com', 'w3.org', 'schema.org', 'wordpress.com', 'wordpress.org',
    'gravatar.com', 'wp.com', 'bootstrapcdn.com', 'jquery.com',
    'google.com', 'facebook.com', 'twitter.com', 'instagram.com',
    'gstatic.com', 'googletagmanager.com', 'google-analytics.com',
    'fontawesome.com', 'cdnjs.cloudflare.com',
}

EXCLUDED_EMAIL_PREFIXES = {
    'noreply', 'no-reply', 'mailer-daemon', 'postmaster',
    'webmaster', 'hostmaster', 'abuse', 'root', 'admin',
}

# File extensions that look like emails but aren't
FALSE_POSITIVE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.ico'}

# Domains to skip in search results
AGGREGATOR_DOMAINS = {
    'autotrader.co.uk', 'cargurus.co.uk', 'motors.co.uk', 'carwow.co.uk',
    'cinch.co.uk', 'heycar.co.uk', 'yell.com', 'facebook.com', 'twitter.com',
    'linkedin.com', 'trustpilot.com', 'companieshouse.gov.uk', 'endole.co.uk',
    'checkatrade.com', 'instagram.com', 'youtube.com', 'tiktok.com',
    'gov.uk', 'yelp.co.uk', 'gumtree.com', 'ebay.co.uk', 'pistonheads.com',
    'confused.com', 'comparethemarket.com', 'gocompare.com',
    'reed.co.uk', 'indeed.co.uk', 'glassdoor.co.uk', 'totaljobs.com',
    'wikipedia.org', 'amazon.co.uk',
    # Data/directory sites that are not dealer websites
    '192.com', 'credencedata.com', 'wombatnation.com', 'laei.uk',
    'opencorporates.com', 'companycheck.co.uk', 'duedil.com', 'dnb.com',
    'bizdb.co.uk', 'ukdata.com', 'checkcompany.co.uk', 'companyinformation.co.uk',
    'find-and-update.company-information.service.gov.uk',
    'cybo.com', 'kompass.com', 'infobel.com', 'hotfrog.co.uk',
    'scoot.co.uk', 'thomsonlocal.com', 'brownbook.net', 'bizwiki.co.uk',
    # Car listing aggregators and directories
    'yelp.com', 'cazoo.co.uk', 'carz4sale.in', 'classiccars.co.uk',
    'local.standard.co.uk', 'yahoosee.com', 'wombatnation.com',
    'freeindex.co.uk', 'bark.com', 'thebestof.co.uk', 'nextdoor.com',
    'citylocal.co.uk', 'accessplace.com', 'thenewsmarket.com',
    'companiesintheuk.co.uk', 'carandclassic.com', 'classicdriver.com',
    'fbhvc.co.uk', 'rhocar.org', 'hybrid-analysis.com', 'eightbar.com',
    'romseyadvertiser.co.uk', 'directory.romseyadvertiser.co.uk',
    # Generic directories
    'yelp.com', 'yelp.co.uk', 'foursquare.com', 'tripadvisor.co.uk',
    'tripadvisor.com', 'pagesjaunes.fr', 'infoisinfo.co.uk',
}

# Domain suffixes to try for domain guessing
DOMAIN_SUFFIXES = ['.co.uk', '.com', '.uk', '.net']
DOMAIN_MODIFIERS = ['', 'cars', 'motors', 'autos', 'vehicles', 'automotive']

# Contact page paths to check
CONTACT_PATHS = ['/contact', '/contact-us', '/about', '/about-us', '/contactus', '/aboutus']

# User agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
]

# Max domain guessing attempts per dealer
MAX_DOMAIN_GUESSES = 20

# Default paths
DEFAULT_DB_PATH = 'data/progress.db'
DEFAULT_OUTPUT_PATH = 'data/output.xlsx'
DEFAULT_LOG_PATH = 'data/scraper.log'

UPLOAD_DIR = 'data/uploads'
SERVER_PORT = 8090
