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
CREATE TABLE IF NOT EXISTS fx_rates (
 day_msk TEXT PRIMARY KEY, usd_rub TEXT NOT NULL
);
"""


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size:
            backup_dir = self.path.parent / 'backups'
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / (self.path.stem + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite')
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

    def rate_for_day(self, day, loader=cbr_usd_rate):
        cached = self.db.execute('SELECT usd_rub FROM fx_rates WHERE day_msk=?',(day,)).fetchone()
        if cached:
            return money(cached['usd_rub'])
        rate = money(loader(day))
        self.db.execute('INSERT INTO fx_rates VALUES (?,?)',(day,str(rate)))
        self.db.commit()
        return rate


RESULT_KINDS = {'Closed P&L', 'TRADE', 'Fee', 'DELIVERY', 'LIQUIDATION', 'ADL',
                'SETTLEMENT', 'Funding', 'Bonus'}


def result_rub(row, include_bonus=False):
    """Classified financial result; transfers and deposits never count as income."""
    kind = row['kind']
    if kind not in RESULT_KINDS or (kind == 'Bonus' and not include_bonus):
        return money(0)
    return money(money(row['amount_usd']) * money(row['rate_rub']))


def calculate(rows, year, include_bonus=False):
    """Illustrative yearly netting and progressive reserve; see README limitations."""
    annual = sorted((r for r in rows if r['day_msk'].startswith(str(year))),
                    key=lambda r: (r['timestamp_ms'], r['id']))
    net = Decimal('0')
    trade_usd = Decimal('0')
    for row in annual:
        net += result_rub(row, include_bonus)
        if row['kind'] in RESULT_KINDS and row['kind'] != 'Bonus':
            trade_usd += money(row['amount_usd'])
    taxable = max(money(net), money(0))
    reserve = money(min(taxable, LIMIT) * LOW_RATE + max(taxable - LIMIT, money(0)) * HIGH_RATE)
    return {'pnl_usd': money(trade_usd), 'pnl_rub': money(net), 'taxable_rub': money(taxable),
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
        writer = csv.writer(file, delimiter=';')
        writer.writerow(['Date MSK','Type','Amount USD','CBR RUB/USD','Amount RUB','Source','Note'])
        for row in rows:
            writer.writerow([row['day_msk'],row['kind'],row['amount_usd'],row['rate_rub'],
                             str(money(money(row['amount_usd']) * money(row['rate_rub']))),
                             row['source'],row['note']])


def export_xlsx(rows, path, year=None, owner=None, include_bonus=False):
    """Two-sheet draft register with live summary and operation formulas."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    owner = owner or {}
    ordered = sorted((r for r in rows if year is None or r['day_msk'].startswith(str(year))),
                     key=lambda r: (r['timestamp_ms'], r['id']))
    period = str(year) if year else 'ВЕСЬ ПЕРИОД'
    book = Workbook()
    summary = book.active; summary.title = 'Сводка за год'
    ops = book.create_sheet('Реестр операций (МСК)')
    ops.append(['№','ID операции','Дата и время UTC','Дата и время МСК','Категория',
                'Тикер','Сумма USD','Комиссия USD','Курс ЦБ RUB/USD',
                'Результат RUB','База года RUB','Резерв RUB','Комментарий'])
    for index, row in enumerate(ordered, 2):
        utc = datetime.fromtimestamp(int(row['timestamp_ms'])/1000,timezone.utc)
        msk = utc.astimezone(MSK)
        note = row.get('note','')
        ticker = note.split('·')[0].strip() if '·' in note else ''
        ops.append([index-1,row['id'],utc.replace(tzinfo=None),msk.replace(tzinfo=None),
                    row['kind'],ticker,float(row['amount_usd']),0.0,
                    float(row['rate_rub']),None,None,None,note])
        ops[f'C{index}'].number_format = 'dd.mm.yyyy hh:mm:ss'
        ops[f'D{index}'].number_format = 'dd.mm.yyyy hh:mm:ss'
        if row['kind'] in RESULT_KINDS and (include_bonus or row['kind'] != 'Bonus'):
            ops[f'J{index}'] = f'=ROUND((G{index}+H{index})*I{index},2)'
        else:
            ops[f'J{index}'] = '=0'
        ops[f'K{index}'] = (f'=J{index}' if index == 2 else
                              f'=IF(YEAR(D{index})=YEAR(D{index-1}),K{index-1}+J{index},J{index})')
        ops[f'L{index}'] = (f'=ROUND(MIN(MAX(K{index},0),2400000)*0.13+'
                               f'MAX(MAX(K{index},0)-2400000,0)*0.15,2)')
    end = len(ordered)+1
    total = end+1
    ops[f'F{total}'] = 'ИТОГО'
    for col in ('G','H','J'):
        ops[f'{col}{total}'] = f'=SUM({col}2:{col}{end})'
    ops.freeze_panes = 'G2'
    ops.auto_filter.ref = f'A1:M{end}'
    ops.print_options.horizontalCentered = True
    ops.sheet_properties.pageSetUpPr.fitToPage = True
    ops.page_setup.fitToWidth = 1
    ops.page_setup.fitToHeight = 0
    ops.page_setup.orientation = 'landscape'
    for col in ('G','H','I','J','K','L'):
        for cell in ops[col][1:]: cell.number_format = '#,##0.00'

    summary.merge_cells('A1:D2')
    summary['A1'] = f'СВОДНЫЙ ФИНАНСОВЫЙ И НАЛОГОВЫЙ РЕГИСТР ЗА {period} ГОД'
    summary['A1'].font = Font(size=15,bold=True,color='FFFFFF')
    summary['A1'].alignment = Alignment(wrap_text=True,vertical='center')
    summary['A1'].fill = PatternFill('solid',fgColor='19324B')
    for row, title, value in [
        (4,'ФИО',owner.get('name','')),(5,'ИНН',owner.get('inn','')),
        (6,'Площадка','Unified Trading Account'),(7,'UID',owner.get('uid','')),
        (8,'Период',period),
        (9,'Сформировано (МСК)',datetime.now(MSK).strftime('%d.%m.%Y %H:%M')),
        (16,'Стартовый депозит USD',owner.get('deposit_usd',0)),
        (17,'Расходы на формирование депозита RUB',owner.get('deposit_cost_rub',0)),
        (18,'Первичный документ',owner.get('deposit_document',''))]:
        summary[f'A{row}']=title; summary[f'C{row}']=value
    summary.merge_cells('A11:D14')
    summary['A11'] = ('Финансовый результат фиксируется в момент закрытия сделки и проведения '
        'начислений по московскому времени. Пересчёт выполняется по курсу ЦБ РФ на дату операции. '
        'Прибыли и убытки сальдируются внутри календарного года, убыток на следующий год не переносится. '
        'Демонстрационный резерв: 13% до 2 400 000 ₽, 15% с превышения. '
        'Перед применением сверить методику с актуальными требованиями.')
    summary['A11'].alignment = Alignment(wrap_text=True,vertical='center')
    summary['A23']='№'; summary['B23']='Показатель'; summary['C23']='Сумма RUB'; summary['D23']='Примечание'
    ref = "'Реестр операций (МСК)'"
    values = [
        ('Доходы (положительные операции)',f'=SUMIF({ref}!J2:J{end},">0",{ref}!J2:J{end})',''),
        ('В том числе бонусы и партнёрские начисления',f'=SUMIF({ref}!E2:E{end},"Bonus",{ref}!J2:J{end})','Отдельная строка'),
        ('Расходы (отрицательные операции)',f'=-SUMIF({ref}!J2:J{end},"<0",{ref}!J2:J{end})',''),
        ('Финансовый результат','=C24-C26','Доходы минус расходы'),
        ('Дополнительная база по прочим счетам',0,'Вводится вручную'),
        ('Совокупная база для расчёта ставки','=MAX(0,C27+C28)','Убыток не переносится'),
        ('База по ставке 13%','=MIN(C29,2400000)',''),
        ('База по ставке 15%','=MAX(0,C29-2400000)',''),
        ('Резерв по ставке 13%','=ROUND(C30*0.13,2)',''),
        ('Резерв по ставке 15%','=ROUND(C31*0.15,2)',''),
        ('ИТОГО РЕЗЕРВ','=SUM(C32:C33)','Проверить перед применением'),
    ]
    for index,(title,value,note) in enumerate(values,24):
        summary[f'A{index}']=index-23
        summary[f'B{index}']=title
        summary[f'C{index}']=value
        summary[f'D{index}']=note
        summary[f'C{index}'].number_format = '#,##0.00 "₽"'
    summary['C28'].fill = PatternFill('solid',fgColor='FFF2CC')
    summary['B34'].font = Font(bold=True)
    summary['C34'].font = Font(bold=True)
    for sheet, header in ((summary,23),(ops,1)):
        for cell in sheet[header]:
            cell.font = Font(color='FFFFFF',bold=True)
            cell.fill = PatternFill('solid',fgColor='19324B')
            cell.alignment = Alignment(wrap_text=True,vertical='center')
        sheet.row_dimensions[header].height = 32
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
    for col,width in {'A':8,'B':54,'C':19,'D':48}.items():
        summary.column_dimensions[col].width=width
    for col,width in {'A':6,'B':22,'C':23,'D':23,'E':19,'F':16,'G':16,
                      'H':16,'I':17,'J':18,'K':18,'L':18,'M':34}.items():
        ops.column_dimensions[col].width=width
    summary.freeze_panes='C24'
    book.save(path)
