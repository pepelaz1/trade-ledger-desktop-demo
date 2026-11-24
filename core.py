"""Offline trade ledger demo. Amounts are illustrative, not tax advice."""
from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.request import urlopen
import xml.etree.ElementTree as ET

MSK = timezone(timedelta(hours=3))
LIMIT = Decimal('2400000')
LOW_RATE = Decimal('0.13')
HIGH_RATE = Decimal('0.15')


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def msk_day(ms):
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).astimezone(MSK).date().isoformat()


def cbr_usd_rate(day):
    """Official historical CBR XML; callers may store the returned rate locally."""
    day_arg = datetime.fromisoformat(day).strftime('%d/%m/%Y')
    with urlopen(f'https://www.cbr.ru/scripts/XML_daily.asp?date_req={day_arg}', timeout=15) as response:
        root = ET.fromstring(response.read())
    for currency in root.findall('Valute'):
        if currency.findtext('CharCode') == 'USD':
            nominal = Decimal(currency.findtext('Nominal'))
            return money(Decimal(currency.findtext('Value').replace(',', '.')) / nominal)
    raise ValueError(f'USD rate unavailable for {day}')


SCHEMA = """
CREATE TABLE IF NOT EXISTS operations (
 id TEXT PRIMARY KEY, timestamp_ms INTEGER NOT NULL, day_msk TEXT NOT NULL,
 kind TEXT NOT NULL, amount_usd TEXT NOT NULL, rate_rub TEXT NOT NULL,
 source TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_operations_day ON operations(day_msk);
"""


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size:
            backup = self.path.with_name(self.path.stem + '.backup.sqlite')
            shutil.copy2(self.path, backup)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def add(self, id, timestamp_ms, kind, amount_usd, rate_rub, source, note=''):
        self.db.execute('INSERT OR IGNORE INTO operations VALUES (?,?,?,?,?,?,?,?)',
                        (id, int(timestamp_ms), msk_day(timestamp_ms), kind,
                         str(money(amount_usd)), str(money(rate_rub)), source, note))
        self.db.commit()

    def rows(self, year=None, month=None, day=None):
        sql = 'SELECT * FROM operations WHERE 1=1'
        args = []
        if year:
            sql += ' AND substr(day_msk,1,4)=?'; args.append(f'{year:04d}')
        if month:
            sql += ' AND substr(day_msk,6,2)=?'; args.append(f'{month:02d}')
        if day:
            sql += ' AND day_msk=?'; args.append(day)
        sql += ' ORDER BY timestamp_ms DESC, id DESC'
        return [dict(row) for row in self.db.execute(sql, args)]

    def close(self):
        self.db.close()


def calculate(rows, year):
    """Illustrative progressive reserve on positive RUB result only."""
    annual = sorted((r for r in rows if r['day_msk'].startswith(str(year))),
                    key=lambda r: (r['timestamp_ms'], r['id']))
    taxable = Decimal('0')
    reserve = Decimal('0')
    pnl_usd = Decimal('0')
    for row in annual:
        amount = money(row['amount_usd'])
        if row['kind'] != 'Closed P&L':
            continue
        pnl_usd += amount
        rub = money(amount * money(row['rate_rub']))
        positive = max(rub, Decimal('0'))
        at_13 = min(positive, max(LIMIT - taxable, Decimal('0')))
        reserve += money(at_13 * LOW_RATE + (positive - at_13) * HIGH_RATE)
        taxable += positive
    return {'pnl_usd': money(pnl_usd), 'taxable_rub': money(taxable),
            'reserve_rub': money(reserve), 'progress': min(float(taxable / LIMIT), 1.0)}


def demo_rows(ledger, year=2026):
    sample = [
        ('2026-11-04T09:15:00+03:00','Closed P&L','186.40','80.12','ETHUSDT · long'),
        ('2026-11-05T11:20:00+03:00','Funding','-2.18','80.23','ETHUSDT'),
        ('2026-11-07T18:40:00+03:00','Closed P&L','-43.15','79.85','BTCUSDT · short'),
        ('2026-11-10T13:05:00+03:00','Closed P&L','312.90','80.41','SOLUSDT · long'),
        ('2026-11-10T13:06:00+03:00','Fee','-4.52','80.41','Trading fee'),
        ('2026-11-14T22:31:00+03:00','Closed P&L','97.35','80.72','XRPUSDT · long'),
        ('2026-11-18T16:08:00+03:00','Closed P&L','224.80','81.03','BTCUSDT · long'),
        ('2026-11-21T10:00:00+03:00','Deposit','800.00','80.96','Demo balance'),
    ]
    for i, (date, kind, amount, rate, note) in enumerate(sample, 1):
        ms = int(datetime.fromisoformat(date).timestamp() * 1000)
        ledger.add(f'demo-{i}', ms, kind, amount, rate, 'demo', note)


def export_csv(rows, path):
    with open(path, 'w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Date MSK','Type','Amount USD','CBR RUB/USD','Amount RUB','Source','Note'])
        for row in rows:
            writer.writerow([row['day_msk'],row['kind'],row['amount_usd'],row['rate_rub'],
                             str(money(money(row['amount_usd']) * money(row['rate_rub']))),
                             row['source'],row['note']])


def export_xlsx(rows, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    book = Workbook()
    ops = book.active; ops.title = 'Operations'
    ops.append(['Date MSK','Type','Amount USD','CBR RUB/USD','Amount RUB','Source','Note'])
    for index, row in enumerate(rows, 2):
        ops.append([row['day_msk'],row['kind'],float(row['amount_usd']),
                    float(row['rate_rub']),f'=C{index}*D{index}',row['source'],row['note']])
    summary = book.create_sheet('Summary')
    summary.append(['Metric','Value'])
    summary.append(['Operations','=COUNTA(Operations!A:A)-1'])
    summary.append(['Total USD','=SUM(Operations!C:C)'])
    summary.append(['Closed P&L USD','=SUMIF(Operations!B:B,"Closed P&L",Operations!C:C)'])
    summary.append(['Positive closed P&L RUB','=SUMIFS(Operations!E:E,Operations!B:B,"Closed P&L",Operations!E:E,">0")'])
    for sheet in book:
        sheet.freeze_panes = 'A2'
        for cell in sheet[1]:
            cell.font = Font(color='FFFFFF', bold=True)
            cell.fill = PatternFill('solid', fgColor='19324B')
        for column in sheet.columns:
            width = min(42, max(14, max(len(str(c.value or '')) for c in column) + 2))
            sheet.column_dimensions[get_column_letter(column[0].column)].width = width
    book.save(path)
