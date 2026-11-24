"""Optional real-data import; requires read-only Bybit API credentials in environment."""
import argparse
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bybit import BybitClient
from core import Ledger, msk_day


def milliseconds(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)


def main():
    parser = argparse.ArgumentParser(description='Import read-only Bybit history into a local SQLite file')
    parser.add_argument('--from-day', required=True, help='UTC YYYY-MM-DD')
    parser.add_argument('--to-day', required=True, help='UTC YYYY-MM-DD, inclusive')
    parser.add_argument('--db', default=str(Path(__file__).parent / 'data' / 'live.sqlite'))
    args = parser.parse_args()
    key = os.environ.get('BYBIT_API_KEY')
    secret = os.environ.get('BYBIT_API_SECRET')
    if not key or not secret:
        parser.error('Set BYBIT_API_KEY and BYBIT_API_SECRET in environment; use read-only key')
    begin = milliseconds(args.from_day)
    finish = milliseconds((date.fromisoformat(args.to_day)+timedelta(days=1)).isoformat()) - 1
    if begin > finish:
        parser.error('--from-day must be before --to-day')
    client = BybitClient(key, secret)
    ledger = Ledger(args.db)
    imported = 0
    try:
        for item in client.iter_history('/v5/position/closed-pnl', begin, finish, category='linear'):
            stamp = int(item.get('updatedTime') or item.get('createdTime'))
            day = msk_day(stamp)
            rate = ledger.rate_for_day(day)
            identifier = 'closed:' + str(item.get('orderId') or item.get('execId') or
                                         f"{item.get('symbol')}:{stamp}:{item.get('closedPnl')}")
            ledger.add(identifier, stamp, 'Closed P&L', item['closedPnl'], rate,
                       'Bybit closed-pnl', item.get('symbol',''))
            imported += 1
        print(f'Imported {imported} closed P&L rows into {args.db}')
        print('Transaction-log importer requires field mapping validation with an account sample.')
    finally:
        ledger.close()


if __name__ == '__main__':
    main()
