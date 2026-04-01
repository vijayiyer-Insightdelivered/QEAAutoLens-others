"""Background scraping engine with SSE event broadcasting."""
import json
import logging
import threading
import time
from queue import Queue

import config
import storage
from main import process_dealer
from utils import RateLimiter, create_session, setup_logging

log = logging.getLogger(__name__)


class ScraperEngine:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DEFAULT_DB_PATH
        self.running = False
        self.stop_requested = False
        self._thread = None
        self._subscribers = []
        self._lock = threading.Lock()
        self.current_dealer = None
        self.processed_count = 0
        self.batch_total = 0

    def start(self, batch_size=100, verify_mx=False, industry='', company_numbers=None):
        if self.running:
            return False
        self.stop_requested = False
        self.processed_count = 0
        self._thread = threading.Thread(
            target=self._run, args=(batch_size, verify_mx, industry, company_numbers), daemon=True
        )
        self._thread.start()
        return True

    def stop(self):
        if not self.running:
            return False
        self.stop_requested = True
        return True

    @property
    def status(self):
        if self.running:
            return 'running'
        return 'idle'

    def subscribe(self):
        q = Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _broadcast(self, event_type, data):
        msg = json.dumps({'type': event_type, **data})
        with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except Exception:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def _run(self, batch_size, verify_mx, industry='', company_numbers=None):
        self.running = True
        setup_logging(verbose=False)
        self._broadcast('status', {'status': 'running'})

        try:
            if company_numbers:
                # Selective mode: reset chosen dealers and scrape them
                storage.reset_dealers_by_numbers(self.db_path, company_numbers)
                dealers = storage.get_dealers_by_numbers(self.db_path, company_numbers)
                self._broadcast('log', {'message': f'Selective scrape: {len(dealers)} companies chosen'})
            else:
                dealers = storage.get_pending_batch(self.db_path, batch_size)
            self.batch_total = len(dealers)

            if not dealers:
                self._broadcast('log', {'message': 'No pending dealers to process'})
                return

            self._broadcast('log', {'message': f'Starting batch of {len(dealers)} dealers'})

            session = create_session()
            rate_limiter = RateLimiter()

            for i, dealer in enumerate(dealers, 1):
                if self.stop_requested:
                    self._broadcast('log', {'message': 'Stopped by user'})
                    break

                cn = dealer['company_number']
                name = dealer['company_name']
                self.current_dealer = name
                self.processed_count = i

                storage.update_dealer(self.db_path, cn, status='processing')
                self._broadcast('dealer_start', {
                    'index': i,
                    'total': len(dealers),
                    'company_number': cn,
                    'company_name': name,
                })

                result = process_dealer(dealer, session, rate_limiter, verify_mx=verify_mx, industry=industry)
                storage.update_dealer(self.db_path, cn, **result)

                emails = result.get('emails_found', [])
                self._broadcast('dealer_done', {
                    'index': i,
                    'total': len(dealers),
                    'company_number': cn,
                    'company_name': name,
                    'status': result.get('status', 'done'),
                    'website_url': result.get('website_url'),
                    'emails_found': emails,
                    'company_status': result.get('company_status'),
                })

            stats = storage.get_progress_stats(self.db_path)
            self._broadcast('batch_done', {
                'stats': stats,
                'message': f'Batch complete. {stats.get("with_emails", 0)} dealers with emails found.',
            })

        except Exception as e:
            log.error(f"Engine error: {e}")
            self._broadcast('error', {'message': str(e)})
        finally:
            self.running = False
            self.current_dealer = None
            self._broadcast('status', {'status': 'idle'})


# Singleton engine instance
engine = ScraperEngine()
