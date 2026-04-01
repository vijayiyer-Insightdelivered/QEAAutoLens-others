#!/usr/bin/env python3
"""
Auto Dealer Email Finder
Scrapes contact emails for UK used car dealers from Companies House data.

Usage:
    python main.py --input data/input.xlsx --batch-size 100
    python main.py --resume
    python main.py --export
"""
import argparse
import logging
import os
import sys
import time

import config
import storage
from domain_guesser import guess_domain
from scraper_companies_house import scrape_companies_house
from scraper_search import search_for_website
from scraper_website import extract_emails_from_website
from utils import RateLimiter, create_session, setup_logging

log = logging.getLogger(__name__)


def process_dealer(dealer, session, rate_limiter, verify_mx=False, industry=''):
    """Run the full scraping pipeline for a single company."""
    company_name = dealer['company_name']
    company_number = dealer['company_number']
    ch_url = dealer['companies_house_url']
    postcode = dealer['postcode']

    result = {
        'status': 'done',
        'company_status': None,
        'officers': [],
        'website_url': None,
        'emails_found': [],
        'email_source': {},
        'error_message': None,
    }

    try:
        # Stage 1: Companies House — verify active, get officers
        log.info(f"[{company_number}] Stage 1: Companies House — {company_name}")
        ch_data = scrape_companies_house(ch_url, session, rate_limiter)
        result['company_status'] = ch_data.get('company_status')
        result['officers'] = ch_data.get('officers', [])

        if result['company_status'] and 'dissolved' in result['company_status'].lower():
            log.info(f"[{company_number}] Company dissolved, skipping further stages")
            result['status'] = 'done'
            return result

        # Stage 2: Web search for website
        log.info(f"[{company_number}] Stage 2: Web search")
        website = search_for_website(company_name, postcode, session, rate_limiter, industry=industry)

        # Stage 3: Domain guessing (only if search found nothing)
        if not website:
            log.info(f"[{company_number}] Stage 3: Domain guessing")
            website = guess_domain(company_name, session, rate_limiter)

        result['website_url'] = website

        # Stage 4: Email extraction
        if website:
            log.info(f"[{company_number}] Stage 4: Email extraction from {website}")
            emails = extract_emails_from_website(website, session, rate_limiter, verify_mx=verify_mx)
            result['emails_found'] = list(emails.keys())
            result['email_source'] = emails
        else:
            log.info(f"[{company_number}] No website found, skipping email extraction")

    except KeyboardInterrupt:
        raise
    except Exception as e:
        log.error(f"[{company_number}] Pipeline error: {e}")
        result['status'] = 'error'
        result['error_message'] = str(e)

    return result


def run_batch(db_path, batch_size, verify_mx=False, industry='', company_numbers=None):
    """Process a batch of pending companies, or specific companies if company_numbers is given."""
    if company_numbers:
        storage.reset_dealers_by_numbers(db_path, company_numbers)
        dealers = storage.get_dealers_by_numbers(db_path, company_numbers)
    else:
        dealers = storage.get_pending_batch(db_path, batch_size)
    if not dealers:
        log.info("No pending dealers to process")
        return 0

    log.info(f"Processing batch of {len(dealers)} dealers")
    session = create_session()
    rate_limiter = RateLimiter()

    processed = 0
    for i, dealer in enumerate(dealers, 1):
        cn = dealer['company_number']
        name = dealer['company_name']

        try:
            # Mark as processing
            storage.update_dealer(db_path, cn, status='processing')

            log.info(f"--- [{i}/{len(dealers)}] {name} (#{cn}) ---")
            result = process_dealer(dealer, session, rate_limiter, verify_mx=verify_mx, industry=industry)

            # Store results
            storage.update_dealer(db_path, cn, **result)
            processed += 1

            emails = result.get('emails_found', [])
            if emails:
                log.info(f"[{cn}] Found {len(emails)} email(s): {', '.join(emails)}")
            else:
                log.info(f"[{cn}] No emails found")

        except KeyboardInterrupt:
            log.info("\nInterrupted! Saving progress...")
            storage.update_dealer(db_path, cn, status='pending')
            break

    # Print summary
    stats = storage.get_progress_stats(db_path)
    log.info(f"\n=== Batch Summary ===")
    log.info(f"Processed: {processed}")
    log.info(f"Total done: {stats.get('done', 0)}")
    log.info(f"With website: {stats.get('with_website', 0)}")
    log.info(f"With emails: {stats.get('with_emails', 0)}")
    log.info(f"Errors: {stats.get('error', 0)}")
    log.info(f"Pending: {stats.get('pending', 0)}")

    return processed


def main():
    parser = argparse.ArgumentParser(description='Company Email Finder')
    parser.add_argument('--input', '-i', help='Input Excel file path')
    parser.add_argument('--batch-size', '-b', type=int, default=100, help='Number of companies to process (default: 100)')
    parser.add_argument('--industry', default='', help='Industry/search term to help find websites (e.g. "car dealer", "plumber", "accountant")')
    parser.add_argument('--resume', '-r', action='store_true', help='Resume from last run (skip Excel import)')
    parser.add_argument('--export', '-e', action='store_true', help='Export database to Excel and exit')
    parser.add_argument('--output', '-o', default=config.DEFAULT_OUTPUT_PATH, help='Output Excel path')
    parser.add_argument('--db', default=config.DEFAULT_DB_PATH, help='SQLite database path')
    parser.add_argument('--verify-mx', action='store_true', help='Verify MX records for found emails')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--stats', action='store_true', help='Show progress stats and exit')
    parser.add_argument('--companies', '-c', nargs='+', help='Specific company numbers to scrape (re-scrapes even if already done)')
    args = parser.parse_args()

    # Ensure data directory exists
    os.makedirs(os.path.dirname(args.db) or '.', exist_ok=True)

    setup_logging(args.verbose)

    # Export only
    if args.export:
        storage.init_db(args.db)
        output = storage.export_to_excel(args.db, args.output)
        print(f"Exported to {output}")
        return

    # Stats only
    if args.stats:
        storage.init_db(args.db)
        stats = storage.get_progress_stats(args.db)
        print(f"Progress: {stats}")
        return

    # Initialize database
    storage.init_db(args.db)

    # Import from Excel if not resuming and not targeting specific companies
    if not args.resume and not args.companies:
        if not args.input:
            parser.error("--input is required (or use --resume / --companies to target existing dealers)")
        if not os.path.exists(args.input):
            parser.error(f"Input file not found: {args.input}")
        storage.import_from_excel(args.input, args.db)

    # Run the scraping batch
    start = time.time()
    processed = run_batch(args.db, args.batch_size, verify_mx=args.verify_mx, industry=args.industry, company_numbers=args.companies)
    elapsed = time.time() - start

    if processed > 0:
        log.info(f"Completed in {elapsed:.0f}s ({elapsed/processed:.1f}s per dealer)")

    # Auto-export after batch
    output = storage.export_to_excel(args.db, args.output)
    log.info(f"Results exported to {output}")


if __name__ == '__main__':
    main()
