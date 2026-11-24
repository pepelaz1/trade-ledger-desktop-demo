import unittest
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bybit import windows
from core import Ledger, calculate, export_csv, msk_day


class LedgerTests(unittest.TestCase):
    def test_msk_rollover(self):
        self.assertEqual(msk_day(1764536400000), '2025-12-01')

    def test_windows_have_no_gap_or_overlap(self):
        result = list(windows(0, 17 * 86400000))
        self.assertEqual(result[0][0], 0)
        self.assertEqual(result[-1][-1], 17 * 86400000)
        for previous, following in zip(result,result[1:]):
            self.assertEqual(previous[1]+1, following[0])
            self.assertLessEqual(previous[1]-previous[0],6*86400000)

    def test_idempotence_and_threshold(self):
        scratch = Path(__file__).parent.parent / 'data'
        scratch.mkdir(exist_ok=True)
        db_path = scratch / f'test-{uuid.uuid4().hex}.sqlite'
        csv_path = scratch / f'test-{uuid.uuid4().hex}.csv'
        try:
            ledger = Ledger(db_path)
            stamp = int(datetime.fromisoformat('2026-01-05T12:00:00+03:00').timestamp()*1000)
            ledger.add('one',stamp,'Closed P&L','20000','100','test')
            ledger.add('one',stamp,'Closed P&L','20000','100','test')
            ledger.add('two',stamp+1000,'Closed P&L','10000','100','test')
            self.assertEqual(len(ledger.rows()),2)
            metrics = calculate(ledger.rows(),2026)
            self.assertEqual(metrics['taxable_rub'],Decimal('3000000.00'))
            self.assertEqual(metrics['reserve_rub'],Decimal('402000.00'))
            ledger.add('loss',stamp+2000,'Closed P&L','-5000','100','test')
            self.assertEqual(calculate(ledger.rows(),2026)['taxable_rub'],Decimal('2500000.00'))
            self.assertEqual(calculate(ledger.rows(),2026)['reserve_rub'],Decimal('327000.00'))
            ledger.add('bonus',stamp+3000,'Bonus','100','100','test')
            self.assertEqual(calculate(ledger.rows(),2026)['taxable_rub'],Decimal('2500000.00'))
            self.assertEqual(calculate(ledger.rows(),2026,include_bonus=True)['taxable_rub'],Decimal('2510000.00'))
            calls=[]
            def lookup(day):
                calls.append(day)
                return '90.12'
            self.assertEqual(ledger.rate_for_day('2026-01-05',lookup),Decimal('90.12'))
            self.assertEqual(ledger.rate_for_day('2026-01-05',lookup),Decimal('90.12'))
            self.assertEqual(calls,['2026-01-05'])
            next_year = int(datetime.fromisoformat('2027-01-01T00:05:00+03:00').timestamp()*1000)
            ledger.add('next-year',next_year,'Closed P&L','10','100','test')
            self.assertEqual(calculate(ledger.rows(),2027)['taxable_rub'],Decimal('1000.00'))
            export_csv(ledger.rows(),csv_path)
            self.assertTrue(csv_path.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertIn(';',csv_path.read_text(encoding='utf-8-sig').splitlines()[0])
            ledger.close()
        finally:
            db_path.unlink(missing_ok=True)
            csv_path.unlink(missing_ok=True)


if __name__ == '__main__': unittest.main()
