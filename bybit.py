"""Minimal read-only Bybit V5 client. No key persistence or trading endpoints."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = 'https://api.bybit.com'


def windows(start_ms, end_ms, days=6):
    """Return inclusive non-overlapping windows shorter than the 7-day API limit."""
    span = days * 86400000
    current = int(start_ms)
    while current <= int(end_ms):
        finish = min(current + span - 1, int(end_ms))
        yield current, finish
        current = finish + 1


class BybitClient:
    def __init__(self, key, secret, base_url=BASE_URL):
        self.key, self.secret, self.base_url = key, secret, base_url

    def get(self, endpoint, params):
        query = urlencode(params)
        stamp = str(int(time.time() * 1000))
        recv = '5000'
        signature = hmac.new(self.secret.encode(),
                             (stamp + self.key + recv + query).encode(), hashlib.sha256).hexdigest()
        request = Request(self.base_url + endpoint + '?' + query, headers={
            'X-BAPI-API-KEY': self.key,
            'X-BAPI-TIMESTAMP': stamp,
            'X-BAPI-RECV-WINDOW': recv,
            'X-BAPI-SIGN': signature,
            'Content-Type': 'application/json',
        })
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
        if payload.get('retCode') != 0:
            raise RuntimeError(f"Bybit API: {payload.get('retMsg')} ({payload.get('retCode')})")
        return payload.get('result') or {}

    def iter_history(self, endpoint, start_ms, end_ms, *, category=None):
        if endpoint not in ('/v5/account/transaction-log', '/v5/position/closed-pnl'):
            raise ValueError('Unsupported read-only endpoint')
        for begin, finish in windows(start_ms, end_ms):
            cursor = None
            seen = set()
            while True:
                params = {'startTime': begin, 'endTime': finish,
                          'limit': 50 if endpoint.endswith('transaction-log') else 100}
                if category:
                    params['category'] = category
                if cursor:
                    params['cursor'] = cursor
                result = self.get(endpoint, params)
                yield from result.get('list', [])
                cursor = result.get('nextPageCursor')
                if not cursor or cursor in seen:
                    break
                seen.add(cursor)
