"""Windows desktop portfolio demo. Run: python app.py"""
import calendar
import os
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import Ledger, calculate, demo_rows, export_csv, export_xlsx, money

ROOT = Path(__file__).parent
DATA = ROOT / 'data'
BG = '#0B1520'; PANEL = '#142435'; BORDER = '#243C50'
TEXT = '#E7F0F7'; MUTED = '#90A7B9'; BLUE = '#3DA8EE'; GREEN = '#49C69C'
MONTHS = ('','Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь')
KINDS = {'Closed P&L':'Закрытый P&L','Funding':'Фандинг','Fee':'Комиссия','Deposit':'Пополнение'}


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Журнал сделок · демо')
        self.root.geometry('1230x820')
        self.root.minsize(1050, 700)
        self.root.configure(bg=BG)
        self.ledger = Ledger(DATA / 'demo.sqlite')
        demo_rows(self.ledger)
        self.year = 2026
        self.month = 11
        self.day = None
        self.build()
        self.refresh()
        self.root.protocol('WM_DELETE_WINDOW', self.close)

    def label(self, parent, text, size=11, color=TEXT, weight='normal', **kw):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size, weight), **kw)

    def button(self, parent, text, action, primary=False):
        return tk.Button(parent, text=text, command=action, bg=BLUE if primary else PANEL,
                         fg=BG if primary else TEXT, activebackground='#60B7EF',
                         activeforeground=BG, relief='flat', borderwidth=0,
                         padx=15, pady=9, cursor='hand2', font=('Segoe UI', 10, 'bold'))

    def panel(self, parent, **kw):
        return tk.Frame(parent, bg=PANEL, highlightbackground=BORDER,
                        highlightthickness=1, **kw)

    def build(self):
        outer = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        outer.pack(fill='both', expand=True)
        top = tk.Frame(outer, bg=BG)
        top.pack(fill='x')
        self.label(top, 'ЖУРНАЛ СДЕЛОК', 21, weight='bold').pack(side='left')
        self.label(top, 'BYBIT · ЛОКАЛЬНОЕ ДЕМО', 10, MUTED).pack(side='left', padx=19, pady=7)
        self.button(top, 'Экспорт XLSX', self.save_xlsx).pack(side='right', padx=(8,0))
        self.button(top, 'Экспорт CSV', self.save_csv).pack(side='right')
        self.label(outer, 'Аналитика сделок на тестовых данных в отдельной локальной базе', 11, MUTED).pack(anchor='w', pady=(3,20))

        stats = tk.Frame(outer, bg=BG)
        stats.pack(fill='x')
        self.cards = []
        for title in ('ЗАКРЫТЫЙ P&L', 'РЕЗЕРВ НАЛОГА · ДЕМО', 'ОПЕРАЦИЙ', 'К ВЫВОДУ · ДЕМО', 'КУРС ЦБ'):
            card = self.panel(stats, padx=17, pady=14)
            card.pack(side='left', fill='x', expand=True, padx=(0,8))
            self.label(card, title, 9, MUTED, 'bold').pack(anchor='w')
            value = self.label(card, '—', 18, TEXT, 'bold')
            value.pack(anchor='w', pady=(7,0))
            self.cards.append(value)

        bar = self.panel(outer, padx=18, pady=12)
        bar.pack(fill='x', pady=15)
        self.label(bar, 'Годовой порог · 2 400 000 ₽', 10, MUTED).pack(anchor='w')
        self.progress = ttk.Progressbar(bar, mode='determinate', maximum=100)
        self.progress.pack(fill='x', pady=(9,3))
        self.progress_text = self.label(bar, '', 9, MUTED)
        self.progress_text.pack(anchor='e')

        body = tk.Frame(outer, bg=BG)
        body.pack(fill='both', expand=True)
        left = self.panel(body, padx=17, pady=15)
        left.pack(side='left', fill='y', padx=(0,13))
        calhead = tk.Frame(left, bg=PANEL)
        calhead.pack(fill='x')
        self.button(calhead, '‹', lambda: self.shift_month(-1)).pack(side='left')
        self.month_title = self.label(calhead, '', 12, weight='bold', width=18)
        self.month_title.pack(side='left')
        self.button(calhead, '›', lambda: self.shift_month(1)).pack(side='left')
        self.calendar_frame = tk.Frame(left, bg=PANEL)
        self.calendar_frame.pack(pady=17)
        self.button(left, 'Все даты', self.clear_day).pack(fill='x')
        self.label(left, 'Нажмите дату для фильтрации.', 9, MUTED).pack(anchor='w', pady=(16,0))
        self.label(left, 'Тестовые данные · без подключения к бирже', 9, MUTED).pack(anchor='w', pady=(4,0))

        right = self.panel(body, padx=16, pady=15)
        right.pack(side='left', fill='both', expand=True)
        header = tk.Frame(right, bg=PANEL)
        header.pack(fill='x', pady=(0,12))
        self.table_title = self.label(header, 'Операции', 14, weight='bold')
        self.table_title.pack(side='left')
        self.count_label = self.label(header, '', 10, MUTED)
        self.count_label.pack(side='right')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Ledger.Treeview', background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=34, borderwidth=0,
                        font=('Segoe UI', 10))
        style.configure('Ledger.Treeview.Heading', background='#1B3448', foreground=TEXT,
                        relief='flat', font=('Segoe UI', 9, 'bold'))
        style.map('Ledger.Treeview', background=[('selected','#23577A')])
        columns = ('date','type','usd','rate','rub','note')
        self.table = ttk.Treeview(right, columns=columns, show='headings', style='Ledger.Treeview')
        widths = (105,115,100,110,115,175)
        names = ('ДАТА · МСК','ТИП','USD','РУБ/USD','РУБ','ДЕТАЛИ')
        for col, name, width in zip(columns,names,widths):
            self.table.heading(col, text=name)
            self.table.column(col, width=width, anchor='w')
        self.table.pack(fill='both', expand=True)
        foot = tk.Frame(outer, bg=BG)
        foot.pack(fill='x', pady=(12,0))
        self.label(foot, 'Расчёт резерва примерный. Для реального применения проверьте правила и исходные данные.', 9, MUTED).pack(side='left')
        self.label(foot, 'Данные на этом ПК', 9, GREEN).pack(side='right')

    def shift_month(self, offset):
        value = self.year * 12 + self.month - 1 + offset
        self.year, index = divmod(value, 12)
        self.month = index + 1
        self.day = None
        self.refresh()

    def clear_day(self):
        self.day = None
        self.refresh()

    def select_day(self, day):
        self.day = None if self.day == day else day
        self.refresh()

    def refresh_calendar(self):
        self.month_title.configure(text=f'{MONTHS[self.month]} {self.year}')
        for widget in self.calendar_frame.winfo_children(): widget.destroy()
        for col, name in enumerate(('ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС')):
            self.label(self.calendar_frame,name,9,MUTED,'bold',width=4).grid(row=0,column=col,pady=4)
        active = {int(r['day_msk'][-2:]) for r in self.ledger.rows(self.year,self.month)}
        for row, week in enumerate(calendar.monthcalendar(self.year,self.month),1):
            for col, day in enumerate(week):
                if not day: continue
                selected = self.day == day
                tk.Button(self.calendar_frame,text=str(day),width=4,height=2,
                          command=lambda d=day:self.select_day(d), relief='flat',border=0,
                          bg=BLUE if selected else ('#21405A' if day in active else PANEL),
                          fg=BG if selected else TEXT, cursor='hand2').grid(row=row,column=col,padx=2,pady=2)

    def refresh(self):
        self.refresh_calendar()
        rows = self.ledger.rows(self.year,self.month,
                                f'{self.year:04d}-{self.month:02d}-{self.day:02d}' if self.day else None)
        all_year = self.ledger.rows(self.year)
        metrics = calculate(all_year,self.year)
        self.cards[0].configure(text=f"${metrics['pnl_usd']:,.2f}")
        self.cards[1].configure(text=f"{metrics['reserve_rub']:,.2f} ₽")
        self.cards[2].configure(text=str(len(all_year)))
        balance = sum((money(r['amount_usd']) for r in all_year), start=money(0))
        reserve_usd = metrics['reserve_rub'] / money('80.96')
        self.cards[3].configure(text=f'${max(money(balance-reserve_usd), money(0)):,.2f}')
        self.cards[4].configure(text='80.96 ₽')
        self.progress['value'] = metrics['progress']*100
        self.progress_text.configure(text=f"{metrics['taxable_rub']:,.2f} ₽ / 2,400,000 ₽")
        self.table_title.configure(text=f'Операции · {MONTHS[self.month]} {self.year}' +
                                   (f' · {self.day}' if self.day else ''))
        self.count_label.configure(text=f'{len(rows)} записей')
        for item in self.table.get_children(): self.table.delete(item)
        for r in rows:
            rub = money(money(r['amount_usd'])*money(r['rate_rub']))
            self.table.insert('', 'end', values=(r['day_msk'],KINDS.get(r['kind'],r['kind']),f"{money(r['amount_usd']):+,.2f}",
                                                  r['rate_rub'],f'{rub:+,.2f}',r['note']))

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')],
                                            initialfile='trade-ledger-demo.csv')
        if path:
            export_csv(self.ledger.rows(self.year),path)
            messagebox.showinfo('Экспорт готов',path)

    def save_xlsx(self):
        path = filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel','*.xlsx')],
                                            initialfile='trade-ledger-demo.xlsx')
        if path:
            export_xlsx(self.ledger.rows(self.year),path)
            messagebox.showinfo('Экспорт готов',path)

    def close(self):
        self.ledger.close(); self.root.destroy()


if __name__ == '__main__':
    App().root.mainloop()
