"""Build the all-in-one demurrage workbook: capture, claim, invoice, track."""
import pickle
from datetime import datetime, timedelta
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule, ColorScaleRule
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

with open('/tmp/data.pkl','rb') as f:
    data = pickle.load(f)
deals = data['deals']
trips = data['trips']

# Normalize
for t in trips:
    t['transporter'] = (t['transporter'] or '').strip().upper() or None
    t['consignee'] = (t['consignee'] or '').strip()

# === Palette ===
NAVY='0B2447'; NAVY_MID='19376D'; GOLD='C9A227'; GOLD_LIGHT='F4E1A4'; GOLD_PALE='FDF4D4'
CREAM='FDFBF7'; GRAY_RULE='E5E7EB'; RED_BG='FCE4E4'; RED_FG='991B1B'
GREEN_BG='DCFCE7'; GREEN_FG='166534'; AMBER_BG='FEF3C7'; AMBER_FG='92400E'
WHITE='FFFFFF'; DARK='111827'; MUTED='6B7280'

thin = Side(style='thin', color=GRAY_RULE)
medium_gold = Side(style='medium', color=GOLD)
border_all = Border(left=thin, right=thin, top=thin, bottom=thin)

def font(size=11, bold=False, color=DARK, italic=False):
    return Font(name='Calibri', size=size, bold=bold, color=color, italic=italic)
def fill(c): return PatternFill('solid', fgColor=c)
def center(wrap=False): return Alignment(horizontal='center', vertical='center', wrap_text=wrap)
def left(wrap=False, indent=0): return Alignment(horizontal='left', vertical='center', wrap_text=wrap, indent=indent)
def right(wrap=False): return Alignment(horizontal='right', vertical='center', wrap_text=wrap)

FMT_USD = '_-[$$-409]* #,##0_-;[Red]-[$$-409]* #,##0_-;_-[$$-409]* "-"??_-;_-@_-'
FMT_USD_DEC = '_-[$$-409]* #,##0.00_-;[Red]-[$$-409]* #,##0.00_-'
FMT_INT = '#,##0;[Red]-#,##0;"-"'
FMT_DATE = 'dd-mmm-yyyy'
FMT_PCT = '0.0%'

wb = Workbook()
wb.remove(wb.active)

# ========== Pre-compute the sample claims from existing trips ==========
# Group all trips by Deal No. → 1 claim per deal (only deals with trips)
deal_trips = defaultdict(list)
for t in trips:
    deal_trips[t['deal']].append(t)

claims = []   # list of dicts
claim_no_by_deal = {}
for i, (deal_no, ts) in enumerate(sorted(deal_trips.items()), start=1):
    cn = f'CLM-2026-{i:03d}'
    claim_no_by_deal[deal_no] = cn
    cmin = min(t['date_loaded'] for t in ts if t['date_loaded'])
    cmax = max(t['offloaded'] or t['arrival'] or t['date_loaded'] for t in ts if t['date_loaded'])
    consignee = ts[0]['consignee']
    deal_meta = next((d for d in deals if d['deal']==deal_no), {})
    claims.append({
        'claim_no': cn,
        'date_issued': datetime(2026,5,15),
        'deal': deal_no,
        'consignee': consignee,
        'bill_to': f'{consignee}\n[Bill-to address]\n[City]\n[Country]',
        'period_from': cmin,
        'period_to': cmax,
        'status': 'Draft',
        'due_date': datetime(2026,5,15)+timedelta(days=30),
        'paid_date': None,
        'notes': f'Demurrage on Deal {deal_no} — {deal_meta.get("route","")}',
    })
# Assign trips to claim_no
for t in trips:
    t['claim_no'] = claim_no_by_deal.get(t['deal'], '')

# ============================================================
# 1. COVER
# ============================================================
cover = wb.create_sheet('Cover')
cover.sheet_view.showGridLines = False
cover.sheet_view.showRowColHeaders = False

for col, w in zip('ABCDEFGHIJ', [3,18,18,18,18,18,18,18,18,3]):
    cover.column_dimensions[col].width = w
for r in range(1, 40):
    cover.row_dimensions[r].height = 18

for r in range(2, 7):
    for c in range(1, 11):
        cover.cell(r, c).fill = fill(NAVY)

cover.merge_cells('B3:I4')
cover.cell(3,2).value = 'DEMURRAGE MANAGEMENT'
cover.cell(3,2).font = font(size=32, bold=True, color=WHITE)
cover.cell(3,2).alignment = Alignment(horizontal='left', vertical='center')

cover.merge_cells('B5:I5')
cover.cell(5,2).value = 'TRUCKING  •  BEIRA → LUSAKA CORRIDOR  •  2026'
cover.cell(5,2).font = font(size=12, bold=True, color=GOLD_LIGHT)
cover.cell(5,2).alignment = Alignment(horizontal='left', vertical='center')

for c in range(1, 11):
    cover.cell(7, c).fill = fill(GOLD)
cover.row_dimensions[7].height = 4

# Workflow stepper
cover.cell(10,2).value = 'WORKFLOW'
cover.cell(10,2).font = font(size=12, bold=True, color=NAVY)

steps = [
    ('1', 'CAPTURE', 'Add trips to the Trips Ledger as they happen.'),
    ('2', 'CLAIM',   'Open the Claims register, add a row, assign trips.'),
    ('3', 'INVOICE', 'Pick the claim on the Invoice tab — print or PDF.'),
    ('4', 'TRACK',   'Update status / paid date — Dashboard reflects it.'),
]
row = 12
for n, title, desc in steps:
    # Number circle
    cover.cell(row, 2).value = n
    cover.cell(row, 2).font = font(size=18, bold=True, color=WHITE)
    cover.cell(row, 2).fill = fill(GOLD)
    cover.cell(row, 2).alignment = center()
    cover.cell(row, 2).border = border_all
    # Title + description
    cover.merge_cells(start_row=row, start_column=3, end_row=row, end_column=9)
    cover.cell(row, 3).value = f'{title}  —  {desc}'
    cover.cell(row, 3).font = font(size=12, color=DARK)
    cover.cell(row, 3).alignment = left(indent=1)
    cover.cell(row, 3).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    cover.row_dimensions[row].height = 30
    row += 1

# KPI cards
cover.cell(22, 2).value = 'PORTFOLIO AT A GLANCE'
cover.cell(22, 2).font = font(size=12, bold=True, color=NAVY)

def kpi(row, col_start, label, value_formula, fmt):
    cover.merge_cells(start_row=row, start_column=col_start, end_row=row, end_column=col_start+1)
    cover.merge_cells(start_row=row+1, start_column=col_start, end_row=row+2, end_column=col_start+1)
    cover.cell(row, col_start).value = label
    cover.cell(row, col_start).font = font(size=9, bold=True, color=WHITE)
    cover.cell(row, col_start).alignment = center()
    cover.cell(row, col_start).fill = fill(NAVY_MID)
    v = cover.cell(row+1, col_start)
    v.value = value_formula
    v.font = font(size=18, bold=True, color=NAVY)
    v.alignment = center()
    v.fill = fill(CREAM)
    v.number_format = fmt
    for rr in range(row, row+3):
        for cc in range(col_start, col_start+2):
            cover.cell(rr, cc).border = Border(
                left=Side(style='thin', color=GOLD), right=Side(style='thin', color=GOLD),
                top=Side(style='thin', color=GOLD), bottom=Side(style='thin', color=GOLD))

kpi(24, 2, 'TOTAL DEMURRAGE',    '=SUM(Trips[Demurrage (USD)])', FMT_USD)
kpi(24, 4, 'INVOICED',           '=SUMIFS(Claims[Amount (USD)],Claims[Status],"Sent")+SUMIFS(Claims[Amount (USD)],Claims[Status],"Paid")', FMT_USD)
kpi(24, 6, 'PAID',               '=SUMIF(Claims[Status],"Paid",Claims[Amount (USD)])', FMT_USD)
kpi(24, 8, 'OUTSTANDING',        '=SUMIF(Claims[Status],"Sent",Claims[Amount (USD)])', FMT_USD)

cover.merge_cells('B36:I36')
cover.cell(36, 2).value = 'CONFIDENTIAL  •  Internal use only'
cover.cell(36, 2).font = font(size=9, italic=True, color=MUTED)
cover.cell(36, 2).alignment = center()

# ============================================================
# 2. COMPANY
# ============================================================
co = wb.create_sheet('Company')
co.sheet_view.showGridLines = False

co.column_dimensions['A'].width = 2
co.column_dimensions['B'].width = 34
co.column_dimensions['C'].width = 50
co.column_dimensions['D'].width = 40

co.merge_cells('B2:D2')
co.cell(2,2).value = 'COMPANY & INVOICING DETAILS'
co.cell(2,2).font = font(size=20, bold=True, color=NAVY)
co.row_dimensions[2].height = 32

co.merge_cells('B3:D3')
co.cell(3,2).value = 'Set once. Everything in invoices and statements is pulled from here.'
co.cell(3,2).font = font(size=10, italic=True, color=MUTED)

for c in range(2, 5):
    co.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))

def co_section(row, title):
    co.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    co.cell(row,2).value = title
    co.cell(row,2).font = font(size=11, bold=True, color=WHITE)
    co.cell(row,2).fill = fill(NAVY_MID)
    co.cell(row,2).alignment = left(indent=1)
    co.row_dimensions[row].height = 22

def co_row(row, label, value, fmt=None, wrap=False):
    co.cell(row, 2).value = label
    co.cell(row, 2).font = font(size=11, color=DARK)
    co.cell(row, 2).alignment = left(indent=1)
    co.cell(row, 2).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    c = co.cell(row, 3)
    c.value = value
    c.font = font(size=11, bold=True, color=NAVY)
    c.alignment = left(indent=1, wrap=wrap)
    c.fill = fill(GOLD_PALE)
    c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    if fmt: c.number_format = fmt
    co.row_dimensions[row].height = 22

co_section(6, 'COMPANY')
co_row(7,  'Legal name',           'Your Company Ltd.')
co_row(8,  'Trading name',         'Your Trading Co.')
co_row(9,  'Address',              'Street, City, Postcode, Country', wrap=True); co.row_dimensions[9].height = 36
co_row(10, 'VAT / TIN',            '—')
co_row(11, 'Phone',                '+00 0 000 0000')
co_row(12, 'Email',                'invoicing@yourco.com')

co_section(14, 'BANK DETAILS (USD)')
co_row(15, 'Bank name',            'Bank of —')
co_row(16, 'Account name',         'Your Company Ltd.')
co_row(17, 'Account number',       '0000000000')
co_row(18, 'IBAN',                 '—')
co_row(19, 'SWIFT / BIC',          '—')
co_row(20, 'Correspondent bank',   '—')

co_section(22, 'INVOICING')
co_row(23, 'Invoice prefix',       'INV-2026-')
co_row(24, 'Next invoice number',  1, fmt=FMT_INT)
co_row(25, 'Payment terms (days)', 30, fmt=FMT_INT)
co_row(26, 'VAT rate',             0, fmt=FMT_PCT)
co_row(27, 'Footer note',          'Thank you for your business. Late payments accrue interest at 1.5% per month.', wrap=True)
co.row_dimensions[27].height = 40

# Named ranges
nm = wb.defined_names
nm['COMPANY_NAME']    = DefinedName('COMPANY_NAME',    attr_text="Company!$C$7")
nm['COMPANY_TRADING'] = DefinedName('COMPANY_TRADING', attr_text="Company!$C$8")
nm['COMPANY_ADDR']    = DefinedName('COMPANY_ADDR',    attr_text="Company!$C$9")
nm['COMPANY_VAT']     = DefinedName('COMPANY_VAT',     attr_text="Company!$C$10")
nm['COMPANY_PHONE']   = DefinedName('COMPANY_PHONE',   attr_text="Company!$C$11")
nm['COMPANY_EMAIL']   = DefinedName('COMPANY_EMAIL',   attr_text="Company!$C$12")
nm['BANK_NAME']       = DefinedName('BANK_NAME',       attr_text="Company!$C$15")
nm['BANK_HOLDER']     = DefinedName('BANK_HOLDER',     attr_text="Company!$C$16")
nm['BANK_ACCT']       = DefinedName('BANK_ACCT',       attr_text="Company!$C$17")
nm['BANK_IBAN']       = DefinedName('BANK_IBAN',       attr_text="Company!$C$18")
nm['BANK_SWIFT']      = DefinedName('BANK_SWIFT',      attr_text="Company!$C$19")
nm['BANK_CORR']       = DefinedName('BANK_CORR',       attr_text="Company!$C$20")
nm['INV_PREFIX']      = DefinedName('INV_PREFIX',      attr_text="Company!$C$23")
nm['INV_NEXT']        = DefinedName('INV_NEXT',        attr_text="Company!$C$24")
nm['PAY_TERMS']       = DefinedName('PAY_TERMS',       attr_text="Company!$C$25")
nm['VAT_RATE']        = DefinedName('VAT_RATE',        attr_text="Company!$C$26")
nm['INV_FOOTER']      = DefinedName('INV_FOOTER',      attr_text="Company!$C$27")

# ============================================================
# 3. ASSUMPTIONS
# ============================================================
asm = wb.create_sheet('Assumptions')
asm.sheet_view.showGridLines = False
asm.column_dimensions['A'].width = 2
asm.column_dimensions['B'].width = 34
asm.column_dimensions['C'].width = 22
asm.column_dimensions['D'].width = 50

asm.merge_cells('B2:D2')
asm.cell(2,2).value = 'ASSUMPTIONS & DEFAULTS'
asm.cell(2,2).font = font(size=20, bold=True, color=NAVY)
asm.row_dimensions[2].height = 32

asm.merge_cells('B3:D3')
asm.cell(3,2).value = 'Edit gold cells to update the entire workbook.'
asm.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 5):
    asm.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))

def asm_section(row, title):
    asm.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    asm.cell(row,2).value = title
    asm.cell(row,2).font = font(size=11, bold=True, color=WHITE)
    asm.cell(row,2).fill = fill(NAVY_MID)
    asm.cell(row,2).alignment = left(indent=1)
    asm.row_dimensions[row].height = 22

def asm_row(row, label, value, note='', fmt=None):
    asm.cell(row, 2).value = label
    asm.cell(row, 2).font = font(size=11)
    asm.cell(row, 2).alignment = left(indent=1)
    asm.cell(row, 2).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    c = asm.cell(row, 3)
    c.value = value
    c.font = font(size=11, bold=True, color=NAVY)
    c.alignment = center()
    c.fill = fill(GOLD_PALE)
    c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    if fmt: c.number_format = fmt
    asm.cell(row, 4).value = note
    asm.cell(row, 4).font = font(size=10, italic=True, color=MUTED)
    asm.cell(row, 4).alignment = left(indent=1)
    asm.row_dimensions[row].height = 20

asm_section(6, 'COMMERCIAL DEFAULTS')
asm_row(7, 'Default laytime (days)', 2, 'Free time at offloading before demurrage accrues.')
asm_row(8, 'Default demurrage rate (USD/day)', 250, 'Per-truck per-day charge once laytime is exceeded.')
asm_row(9, 'Currency', 'USD', 'Reporting currency.')
asm_row(10, 'FX rate (local → USD)', 1.00, '1.00 if invoices already in USD.', fmt='0.0000')

asm_section(12, 'REPORTING PERIOD')
asm_row(13, 'Period start', datetime(2026,1,1), 'Inclusive.', fmt=FMT_DATE)
asm_row(14, 'Period end',   datetime(2026,4,30), 'Inclusive.', fmt=FMT_DATE)
asm_row(15, 'Report issued', datetime(2026,5,15), '', fmt=FMT_DATE)

asm_section(17, 'TOLERANCES & FLAGS')
asm_row(18, 'Outlier threshold (waiting days)', 7, 'Trips above this are highlighted.')
asm_row(19, 'Sanity tolerance (days)', 0, 'Days of grace before flagging date inconsistency.')

nm['DEF_LAYTIME']  = DefinedName('DEF_LAYTIME',  attr_text="Assumptions!$C$7")
nm['DEF_RATE']     = DefinedName('DEF_RATE',     attr_text="Assumptions!$C$8")
nm['CCY']          = DefinedName('CCY',          attr_text="Assumptions!$C$9")
nm['FX']           = DefinedName('FX',           attr_text="Assumptions!$C$10")
nm['PERIOD_START'] = DefinedName('PERIOD_START', attr_text="Assumptions!$C$13")
nm['PERIOD_END']   = DefinedName('PERIOD_END',   attr_text="Assumptions!$C$14")
nm['OUTLIER_DAYS'] = DefinedName('OUTLIER_DAYS', attr_text="Assumptions!$C$18")

# ============================================================
# 4. DEALS
# ============================================================
dm = wb.create_sheet('Deals')
dm.sheet_view.showGridLines = False
for col, w in zip('ABCDEFGHIJK', [2,12,30,20,16,16,12,12,18,18,16]):
    dm.column_dimensions[col].width = w

dm.merge_cells('B2:K2')
dm.cell(2,2).value = 'DEALS MASTER'
dm.cell(2,2).font = font(size=20, bold=True, color=NAVY)
dm.row_dimensions[2].height = 32

dm.merge_cells('B3:K3')
dm.cell(3,2).value = 'Register of all demurrage deals — rates and laytime feed the Trips Ledger.'
dm.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 12):
    dm.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))

headers = ['Deal No.','Consignee','Route','Loading Port','Destination','Product',
           'Laytime (days)','Rate (USD/day)','Transport (USD/m³)','Transporter']
hr = 6
for i, h in enumerate(headers):
    c = dm.cell(hr, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
dm.row_dimensions[hr].height = 36

for i, d in enumerate(deals):
    r = hr + 1 + i
    vals = [d['deal'], d['consignee'], d['route'], d['loading_port'], d['destination'],
            d['product'], d['laytime'], d['rate'], d['transport_rate'], d['transporter']]
    for j, v in enumerate(vals):
        c = dm.cell(r, 2+j)
        c.value = v
        c.font = font(size=10)
        c.alignment = left(indent=1) if j in (1,2,3,4,5,9) else center()
        c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        if i % 2 == 0: c.fill = fill(CREAM)
    dm.cell(r, 2+6).number_format = FMT_INT
    dm.cell(r, 2+7).number_format = FMT_USD
    dm.cell(r, 2+8).number_format = '#,##0.00;"-"'

tbl = Table(displayName='Deals', ref=f'B{hr}:K{hr+len(deals)}')
tbl.tableStyleInfo = TableStyleInfo(name='TableStyleLight1', showRowStripes=False, showColumnStripes=False)
dm.add_table(tbl)
dm.freeze_panes = 'B7'

# ============================================================
# 5. TRIPS LEDGER (with Claim No. column added)
# ============================================================
tl = wb.create_sheet('Trips Ledger')
tl.sheet_view.showGridLines = False

trip_cols = [
    ('Deal No.', 10), ('Claim No.', 13), ('Consignee', 22), ('Date Loaded', 13),
    ('Loading Port', 12), ('Destination', 12), ('Product', 9),
    ('Truck No.', 13), ('Trailer Reg.', 13), ('Transporter', 13),
    ('Driver', 20), ('Arrival', 13), ('Offloaded', 13),
    ('Waiting (d)', 10), ('Laytime (d)', 10), ('Excess (d)', 10),
    ('Rate (USD)', 11), ('Demurrage (USD)', 14),
    ('Status', 13), ('Sanity', 16), ('Month', 10),
]
tl.column_dimensions['A'].width = 2
for i, (h, w) in enumerate(trip_cols):
    tl.column_dimensions[get_column_letter(2+i)].width = w

last_col_letter = get_column_letter(2+len(trip_cols)-1)
tl.merge_cells(f'B2:{last_col_letter}2')
tl.cell(2,2).value = 'TRIPS LEDGER'
tl.cell(2,2).font = font(size=20, bold=True, color=NAVY)
tl.row_dimensions[2].height = 32

tl.merge_cells(f'B3:{last_col_letter}3')
tl.cell(3,2).value = ('All truck movements. New rows added at the bottom inherit formulas automatically. '
                     'Assign a Claim No. to bundle trips into a claim.')
tl.cell(3,2).font = font(size=10, italic=True, color=MUTED)

for c in range(2, 2+len(trip_cols)):
    tl.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))

hr = 6
for i, (h, _) in enumerate(trip_cols):
    c = tl.cell(hr, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
tl.row_dimensions[hr].height = 36

# Column letters (table starts at col B=2):
# B=Deal C=Claim D=Consignee E=Loaded F=LoadPort G=Dest H=Product
# I=Truck J=Trailer K=Transp L=Driver M=Arr N=Off O=Wait P=Laytime
# Q=Excess R=Rate S=Demurrage T=Status U=Sanity V=Month
for i, t in enumerate(trips):
    r = hr + 1 + i
    tl.cell(r, 2).value = t['deal']
    tl.cell(r, 3).value = t['claim_no']
    tl.cell(r, 4).value = t['consignee']
    tl.cell(r, 5).value = t['date_loaded']
    tl.cell(r, 6).value = t['loading_port']
    tl.cell(r, 7).value = t['destination']
    tl.cell(r, 8).value = t['product']
    tl.cell(r, 9).value = t['truck']
    tl.cell(r,10).value = t['trailer']
    tl.cell(r,11).value = t['transporter']
    tl.cell(r,12).value = t['driver']
    tl.cell(r,13).value = t['arrival']
    tl.cell(r,14).value = t['offloaded']
    tl.cell(r,15).value = f'=IF(OR(L{r}="",M{r}=""),"",M{r}-L{r})'                        # Waiting = Offloaded - Arrival
    tl.cell(r,16).value = f'=IFERROR(VLOOKUP(B{r},Deals[#All],7,FALSE),DEF_LAYTIME)'      # Laytime
    tl.cell(r,17).value = f'=IF(O{r}="","",MAX(0,O{r}-P{r}))'                             # Excess
    tl.cell(r,18).value = f'=IFERROR(VLOOKUP(B{r},Deals[#All],8,FALSE),DEF_RATE)'         # Rate
    tl.cell(r,19).value = f'=IF(Q{r}="","",Q{r}*R{r})'                                    # Demurrage
    tl.cell(r,20).value = f'=IF(O{r}="","PENDING",IF(Q{r}>0,"DEMURRAGE","ON-TIME"))'      # Status
    tl.cell(r,21).value = (f'=IF(AND(E{r}<>"",M{r}<>"",M{r}<E{r}),"⚠ Arr<Loaded",'
                          f'IF(AND(M{r}<>"",N{r}<>"",N{r}<M{r}),"⚠ Off<Arr","OK"))')
    tl.cell(r,22).value = f'=IF(E{r}="","",TEXT(E{r},"yyyy-mm"))'

last_row = hr + len(trips)

# Styles
for r in range(hr+1, last_row+1):
    for j in range(len(trip_cols)):
        c = tl.cell(r, 2+j)
        c.font = font(size=10)
        c.border = Border(left=Side(style='thin', color=GRAY_RULE),
                          right=Side(style='thin', color=GRAY_RULE),
                          top=Side(style='thin', color=GRAY_RULE),
                          bottom=Side(style='thin', color=GRAY_RULE))
        c.alignment = left(indent=1)
    tl.cell(r, 2).alignment = center()    # Deal
    tl.cell(r, 3).alignment = center()    # Claim
    tl.cell(r, 5).number_format = FMT_DATE; tl.cell(r, 5).alignment = center()
    tl.cell(r,13).number_format = FMT_DATE; tl.cell(r,13).alignment = center()
    tl.cell(r,14).number_format = FMT_DATE; tl.cell(r,14).alignment = center()
    for col in (15,16,17): tl.cell(r,col).number_format = FMT_INT; tl.cell(r,col).alignment = center()
    tl.cell(r,18).number_format = FMT_USD; tl.cell(r,18).alignment = right()
    tl.cell(r,19).number_format = FMT_USD; tl.cell(r,19).alignment = right()
    for col in (20,21,22): tl.cell(r,col).alignment = center()

# Excel table
trip_ref = f'B{hr}:{last_col_letter}{last_row}'
tt = Table(displayName='Trips', ref=trip_ref)
tt.tableStyleInfo = TableStyleInfo(name='TableStyleLight1', showRowStripes=True, showColumnStripes=False)
tl.add_table(tt)

# Conditional formatting
status_range = f'T{hr+1}:T{last_row}'
tl.conditional_formatting.add(status_range,
    CellIsRule(operator='equal', formula=['"DEMURRAGE"'], fill=fill(RED_BG), font=font(bold=True, color=RED_FG)))
tl.conditional_formatting.add(status_range,
    CellIsRule(operator='equal', formula=['"ON-TIME"'], fill=fill(GREEN_BG), font=font(bold=True, color=GREEN_FG)))
tl.conditional_formatting.add(status_range,
    CellIsRule(operator='equal', formula=['"PENDING"'], fill=fill(GOLD_PALE), font=font(bold=True, color=NAVY)))

wait_range = f'O{hr+1}:O{last_row}'
tl.conditional_formatting.add(wait_range,
    ColorScaleRule(start_type='num', start_value=0, start_color='DCFCE7',
                   mid_type='num', mid_value=7, mid_color='FEF3C7',
                   end_type='num', end_value=15, end_color='FCA5A5'))
tl.conditional_formatting.add(f'U{hr+1}:U{last_row}',
    FormulaRule(formula=[f'LEFT(U{hr+1},1)="⚠"'], fill=fill(RED_BG), font=font(bold=True, color=RED_FG)))

# Data validation: Claim No. column choices come from Claims table
dv_claim = DataValidation(type='list', formula1='=Claims[Claim No.]', allow_blank=True)
dv_claim.add(f'C{hr+1}:C{hr+500}')   # extend room for new trips
tl.add_data_validation(dv_claim)

# Totals row
tot = last_row + 2
for j in range(2, 2+len(trip_cols)):
    tl.cell(tot, j).fill = fill(NAVY)
    tl.cell(tot, j).font = font(bold=True, color=WHITE)
tl.cell(tot, 2).value = 'TOTAL'
tl.cell(tot, 2).alignment = center()
tl.cell(tot,15).value = '=SUBTOTAL(109,Trips[Waiting (d)])'; tl.cell(tot,15).number_format=FMT_INT; tl.cell(tot,15).alignment=center()
tl.cell(tot,17).value = '=SUBTOTAL(109,Trips[Excess (d)])';  tl.cell(tot,17).number_format=FMT_INT; tl.cell(tot,17).alignment=center()
tl.cell(tot,19).value = '=SUBTOTAL(109,Trips[Demurrage (USD)])'; tl.cell(tot,19).number_format=FMT_USD; tl.cell(tot,19).alignment=right()

tl.freeze_panes = f'E{hr+1}'
tl.page_setup.orientation = tl.ORIENTATION_LANDSCAPE
tl.page_setup.fitToWidth = 1
tl.sheet_properties.pageSetUpPr.fitToPage = True

# ============================================================
# 6. CLAIMS REGISTER
# ============================================================
cl = wb.create_sheet('Claims')
cl.sheet_view.showGridLines = False

cl_cols = [
    ('Claim No.', 14), ('Issue Date', 13), ('Deal No.', 11),
    ('Consignee', 24), ('Bill-To Address', 32),
    ('Period From', 13), ('Period To', 13),
    ('# Trips', 9), ('Amount (USD)', 14), ('Currency', 10),
    ('Status', 12), ('Due Date', 13), ('Paid Date', 13),
    ('Days Overdue', 12), ('Aging', 12), ('Notes', 32),
]
cl.column_dimensions['A'].width = 2
for i, (h, w) in enumerate(cl_cols):
    cl.column_dimensions[get_column_letter(2+i)].width = w
last_col_cl = get_column_letter(2+len(cl_cols)-1)

cl.merge_cells(f'B2:{last_col_cl}2')
cl.cell(2,2).value = 'CLAIMS REGISTER'
cl.cell(2,2).font = font(size=20, bold=True, color=NAVY)
cl.row_dimensions[2].height = 32

cl.merge_cells(f'B3:{last_col_cl}3')
cl.cell(3,2).value = ('One row per claim. Add a row, assign matching trips in the Trips Ledger to this Claim No., '
                     'then preview / print on the Invoice tab.')
cl.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 2+len(cl_cols)):
    cl.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))

hr = 6
for i, (h, _) in enumerate(cl_cols):
    c = cl.cell(hr, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
cl.row_dimensions[hr].height = 36

# Column letters: B=ClaimNo C=Issue D=Deal E=Consignee F=BillTo G=From H=To
# I=#Trips J=Amount K=CCY L=Status M=Due N=Paid O=Overdue P=Aging Q=Notes
for i, cm in enumerate(claims):
    r = hr + 1 + i
    cl.cell(r, 2).value = cm['claim_no']
    cl.cell(r, 3).value = cm['date_issued']
    cl.cell(r, 4).value = cm['deal']
    cl.cell(r, 5).value = f'=IFERROR(VLOOKUP(D{r},Deals[#All],2,FALSE),"")'
    cl.cell(r, 6).value = cm['bill_to']
    cl.cell(r, 7).value = cm['period_from']
    cl.cell(r, 8).value = cm['period_to']
    cl.cell(r, 9).value = f'=COUNTIF(Trips[Claim No.],B{r})'
    cl.cell(r,10).value = f'=SUMIF(Trips[Claim No.],B{r},Trips[Demurrage (USD)])'
    cl.cell(r,11).value = '=CCY'
    cl.cell(r,12).value = cm['status']
    cl.cell(r,13).value = f'=C{r}+PAY_TERMS'
    cl.cell(r,14).value = cm['paid_date']
    cl.cell(r,15).value = (f'=IF(L{r}="Paid",0,IF(L{r}="Sent",MAX(0,TODAY()-M{r}),""))')
    cl.cell(r,16).value = (f'=IF(L{r}="Paid","Paid",'
                          f'IF(L{r}<>"Sent","",'
                          f'IF(O{r}<=0,"Current",'
                          f'IF(O{r}<=30,"1-30",'
                          f'IF(O{r}<=60,"31-60","60+")))))')
    cl.cell(r,17).value = cm['notes']

last_row_cl = hr + len(claims)

# Styles
for r in range(hr+1, last_row_cl+1):
    for j in range(len(cl_cols)):
        c = cl.cell(r, 2+j)
        c.font = font(size=10)
        c.border = Border(left=Side(style='thin', color=GRAY_RULE),
                          right=Side(style='thin', color=GRAY_RULE),
                          top=Side(style='thin', color=GRAY_RULE),
                          bottom=Side(style='thin', color=GRAY_RULE))
        c.alignment = left(indent=1, wrap=True)
    cl.cell(r, 2).alignment = center()
    cl.cell(r, 3).number_format = FMT_DATE; cl.cell(r, 3).alignment = center()
    cl.cell(r, 4).alignment = center()
    cl.cell(r, 7).number_format = FMT_DATE; cl.cell(r, 7).alignment = center()
    cl.cell(r, 8).number_format = FMT_DATE; cl.cell(r, 8).alignment = center()
    cl.cell(r, 9).number_format = FMT_INT;  cl.cell(r, 9).alignment = center()
    cl.cell(r,10).number_format = FMT_USD;  cl.cell(r,10).alignment = right()
    cl.cell(r,11).alignment = center()
    cl.cell(r,12).alignment = center()
    cl.cell(r,13).number_format = FMT_DATE; cl.cell(r,13).alignment = center()
    cl.cell(r,14).number_format = FMT_DATE; cl.cell(r,14).alignment = center()
    cl.cell(r,15).number_format = FMT_INT;  cl.cell(r,15).alignment = center()
    cl.cell(r,16).alignment = center()
    cl.row_dimensions[r].height = 32

# Excel table
claim_ref = f'B{hr}:{last_col_cl}{last_row_cl}'
tt2 = Table(displayName='Claims', ref=claim_ref)
tt2.tableStyleInfo = TableStyleInfo(name='TableStyleLight1', showRowStripes=True)
cl.add_table(tt2)

# Data validation for Status
dv_status = DataValidation(type='list', formula1='"Draft,Sent,Paid,Cancelled"', allow_blank=False)
dv_status.add(f'L{hr+1}:L{hr+500}')
cl.add_data_validation(dv_status)

# Conditional formatting on Status
status_rng = f'L{hr+1}:L{last_row_cl}'
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Paid"'], fill=fill(GREEN_BG), font=font(bold=True, color=GREEN_FG)))
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Sent"'], fill=fill(AMBER_BG), font=font(bold=True, color=AMBER_FG)))
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Draft"'], fill=fill(GOLD_PALE), font=font(bold=True, color=NAVY)))
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Cancelled"'], fill=fill(GRAY_HEADER:='F3F4F6'), font=font(italic=True, color=MUTED)))

# Aging conditional formatting
aging_rng = f'P{hr+1}:P{last_row_cl}'
cl.conditional_formatting.add(aging_rng,
    CellIsRule(operator='equal', formula=['"Current"'], fill=fill(GREEN_BG), font=font(bold=True, color=GREEN_FG)))
cl.conditional_formatting.add(aging_rng,
    CellIsRule(operator='equal', formula=['"1-30"'], fill=fill(AMBER_BG), font=font(bold=True, color=AMBER_FG)))
cl.conditional_formatting.add(aging_rng,
    CellIsRule(operator='equal', formula=['"31-60"'], fill=fill('FFE0B2'), font=font(bold=True, color='8B4513')))
cl.conditional_formatting.add(aging_rng,
    CellIsRule(operator='equal', formula=['"60+"'], fill=fill(RED_BG), font=font(bold=True, color=RED_FG)))
cl.conditional_formatting.add(aging_rng,
    CellIsRule(operator='equal', formula=['"Paid"'], fill=fill(GREEN_BG), font=font(bold=True, color=GREEN_FG)))

# Totals
tot = last_row_cl + 2
for j in range(2, 2+len(cl_cols)):
    cl.cell(tot, j).fill = fill(NAVY); cl.cell(tot, j).font = font(bold=True, color=WHITE)
cl.cell(tot, 2).value = 'TOTAL'
cl.cell(tot, 2).alignment = center()
cl.cell(tot, 9).value = '=SUBTOTAL(109,Claims[# Trips])'; cl.cell(tot,9).number_format=FMT_INT; cl.cell(tot,9).alignment=center()
cl.cell(tot,10).value = '=SUBTOTAL(109,Claims[Amount (USD)])'; cl.cell(tot,10).number_format=FMT_USD; cl.cell(tot,10).alignment=right()

cl.freeze_panes = f'C{hr+1}'
cl.page_setup.orientation = cl.ORIENTATION_LANDSCAPE
cl.page_setup.fitToWidth = 1
cl.sheet_properties.pageSetUpPr.fitToPage = True

# ============================================================
# 7. INVOICE
# ============================================================
inv = wb.create_sheet('Invoice')
inv.sheet_view.showGridLines = False
inv.sheet_view.showRowColHeaders = False

# Column setup — A is margin, B-K is body, L is margin
widths = {'A':2, 'B':5, 'C':16, 'D':16, 'E':16, 'F':10, 'G':10, 'H':10, 'I':10, 'J':14, 'K':16, 'L':2}
for col, w in widths.items():
    inv.column_dimensions[col].width = w

# Navy header band
for r in range(2, 8):
    for c in range(1, 13):
        inv.cell(r, c).fill = fill(NAVY)

# Left: Company block
inv.merge_cells('B3:E3')
inv.cell(3, 2).value = '=COMPANY_NAME'
inv.cell(3, 2).font = font(size=18, bold=True, color=WHITE)
inv.cell(3, 2).alignment = left()

inv.merge_cells('B4:E4')
inv.cell(4, 2).value = '=COMPANY_ADDR'
inv.cell(4, 2).font = font(size=9, color=GOLD_LIGHT)
inv.cell(4, 2).alignment = left()

inv.merge_cells('B5:E5')
inv.cell(5, 2).value = '="VAT/TIN: "&COMPANY_VAT&"   •   "&COMPANY_EMAIL&"   •   "&COMPANY_PHONE'
inv.cell(5, 2).font = font(size=9, color=GOLD_LIGHT)
inv.cell(5, 2).alignment = left()

# Right: "INVOICE" big
inv.merge_cells('H3:K3')
inv.cell(3, 8).value = 'INVOICE'
inv.cell(3, 8).font = font(size=32, bold=True, color=GOLD_LIGHT)
inv.cell(3, 8).alignment = right()

inv.merge_cells('H5:K5')
inv.cell(5, 8).value = '=COMPANY_TRADING'
inv.cell(5, 8).font = font(size=10, color=WHITE, italic=True)
inv.cell(5, 8).alignment = right()

# Gold rule below the header
for c in range(1, 13):
    inv.cell(8, c).fill = fill(GOLD)
inv.row_dimensions[8].height = 4

# === Claim picker row ===
inv.cell(10, 2).value = 'CLAIM No.'
inv.cell(10, 2).font = font(size=10, bold=True, color=MUTED)
inv.cell(10, 2).alignment = left()
inv.merge_cells('B11:C11')
inv.cell(11, 2).value = claims[0]['claim_no'] if claims else None
inv.cell(11, 2).font = font(size=20, bold=True, color=NAVY)
inv.cell(11, 2).fill = fill(GOLD_PALE)
inv.cell(11, 2).alignment = center()
for cc in range(2, 4):
    inv.cell(11, cc).border = Border(left=medium_gold, right=medium_gold, top=medium_gold, bottom=medium_gold)

dv_inv_claim = DataValidation(type='list', formula1='=Claims[Claim No.]', allow_blank=False)
dv_inv_claim.add('B11')
inv.add_data_validation(dv_inv_claim)

# Invoice metadata block (right)
def meta_row(row, label, formula, fmt=None):
    inv.merge_cells(start_row=row, start_column=8, end_row=row, end_column=9)
    inv.cell(row, 8).value = label
    inv.cell(row, 8).font = font(size=9, bold=True, color=MUTED)
    inv.cell(row, 8).alignment = right()
    inv.merge_cells(start_row=row, start_column=10, end_row=row, end_column=11)
    c = inv.cell(row, 10)
    c.value = formula
    c.font = font(size=11, bold=True, color=NAVY)
    c.alignment = right()
    c.border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    if fmt: c.number_format = fmt

# Invoice number = INV_PREFIX & (INV_NEXT + claim row index - 1)
# We resolve the row index of the picked claim with MATCH, so each claim has a stable invoice number.
inv_no_formula = '=INV_PREFIX & TEXT(INV_NEXT + MATCH($B$11, Claims[Claim No.], 0) - 1, "000")'
meta_row(10, 'Invoice No.', inv_no_formula)
meta_row(11, 'Invoice Date', '=IFERROR(VLOOKUP($B$11,Claims[#All],2,FALSE),TODAY())', FMT_DATE)
meta_row(12, 'Due Date',     '=IFERROR(VLOOKUP($B$11,Claims[#All],12,FALSE),TODAY()+PAY_TERMS)', FMT_DATE)
meta_row(13, 'Currency',     '=CCY')
meta_row(14, 'Status',       '=IFERROR(VLOOKUP($B$11,Claims[#All],11,FALSE),"")')

# === Bill-To block ===
inv.cell(14, 2).value = 'BILL TO'
inv.cell(14, 2).font = font(size=9, bold=True, color=MUTED)
inv.cell(14, 2).alignment = left()

inv.merge_cells('B15:F15')
inv.cell(15, 2).value = '=IFERROR(VLOOKUP($B$11,Claims[#All],4,FALSE),"")'
inv.cell(15, 2).font = font(size=13, bold=True, color=NAVY)
inv.cell(15, 2).alignment = left()

inv.merge_cells('B16:F19')
inv.cell(16, 2).value = '=IFERROR(VLOOKUP($B$11,Claims[#All],5,FALSE),"")'
inv.cell(16, 2).font = font(size=10, color=DARK)
inv.cell(16, 2).alignment = left(wrap=True)
for r in range(16, 20):
    inv.row_dimensions[r].height = 16

# Subject / Reference
inv.cell(17, 8).value = 'CLAIM REFERENCE'
inv.cell(17, 8).font = font(size=9, bold=True, color=MUTED)
inv.cell(17, 8).alignment = left()
inv.merge_cells('H18:K18')
inv.cell(18, 8).value = '=$B$11'
inv.cell(18, 8).font = font(size=11, bold=True, color=NAVY)
inv.cell(18, 8).alignment = left()

inv.cell(19, 8).value = 'PERIOD'
inv.cell(19, 8).font = font(size=9, bold=True, color=MUTED)
inv.cell(19, 8).alignment = left()
inv.merge_cells('H20:K20')
inv.cell(20, 8).value = ('=TEXT(IFERROR(VLOOKUP($B$11,Claims[#All],6,FALSE),""),"dd-mmm-yyyy") '
                       '&" → "&TEXT(IFERROR(VLOOKUP($B$11,Claims[#All],7,FALSE),""),"dd-mmm-yyyy")')
inv.cell(20, 8).font = font(size=11, bold=True, color=NAVY)
inv.cell(20, 8).alignment = left()

# Subject line (full width)
inv.merge_cells('B22:K22')
inv.cell(22, 2).value = ('="Subject:  Demurrage charges — Deal "&IFERROR(VLOOKUP($B$11,Claims[#All],3,FALSE),"")'
                       '&" — "&IFERROR(VLOOKUP($B$11,Claims[#All],4,FALSE),"")')
inv.cell(22, 2).font = font(size=11, bold=True, color=DARK)
inv.cell(22, 2).alignment = left()
inv.cell(22, 2).fill = fill(GOLD_PALE)
inv.cell(22, 2).border = Border(top=Side(style='thin', color=GOLD), bottom=Side(style='thin', color=GOLD),
                                left=Side(style='thin', color=GOLD), right=Side(style='thin', color=GOLD))
inv.row_dimensions[22].height = 24

# === Line items table ===
LI_HEADERS = ['#', 'Date Loaded', 'Truck No.', 'Driver', 'Waiting (d)', 'Laytime (d)', 'Excess (d)', 'Rate', 'Amount (USD)']
li_hdr_row = 25
# Place headers across cols B..J (9 cols). Last col K reserved.
# col indices: B=2, C=3, D=4, E=5, F=6, G=7, H=8, I=9, J=10
li_cols = list(range(2, 11))  # B..J
for col_idx, h in zip(li_cols, LI_HEADERS):
    c = inv.cell(li_hdr_row, col_idx)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
inv.row_dimensions[li_hdr_row].height = 32

# 30 line item rows max
N_LI = 30
for k in range(1, N_LI+1):
    r = li_hdr_row + k
    # k-th matching trip where Trips[Claim No.] = picked
    def kth(field):
        return (f'=IFERROR(INDEX(Trips[{field}],SMALL(IF(Trips[Claim No.]=$B$11,'
                f'ROW(Trips[Claim No.])-MIN(ROW(Trips[Claim No.]))+1),{k})),"")')
    # # column = sequential when amount exists
    inv.cell(r, 2).value = f'=IF(J{r}="","",{k})'
    inv.cell(r, 3).value = kth('Date Loaded')
    inv.cell(r, 4).value = kth('Truck No.')
    inv.cell(r, 5).value = kth('Driver')
    inv.cell(r, 6).value = kth('Waiting (d)')
    inv.cell(r, 7).value = kth('Laytime (d)')
    inv.cell(r, 8).value = kth('Excess (d)')
    inv.cell(r, 9).value = kth('Rate (USD)')
    inv.cell(r,10).value = kth('Demurrage (USD)')

    # Styles
    for col in li_cols:
        cc = inv.cell(r, col)
        cc.font = font(size=10)
        cc.border = Border(left=Side(style='thin', color=GRAY_RULE),
                           right=Side(style='thin', color=GRAY_RULE),
                           top=Side(style='thin', color=GRAY_RULE),
                           bottom=Side(style='thin', color=GRAY_RULE))
        cc.alignment = left(indent=1)
        if k % 2 == 0:
            cc.fill = fill(CREAM)
    inv.cell(r, 2).alignment = center()
    inv.cell(r, 3).number_format = FMT_DATE; inv.cell(r, 3).alignment = center()
    inv.cell(r, 4).alignment = center()
    for col in (6, 7, 8):
        inv.cell(r, col).number_format = FMT_INT
        inv.cell(r, col).alignment = center()
    inv.cell(r, 9).number_format = FMT_USD;  inv.cell(r, 9).alignment = right()
    inv.cell(r,10).number_format = FMT_USD;  inv.cell(r,10).alignment = right()

# Totals box on the right (cols I,J)
tot_start = li_hdr_row + N_LI + 2

def tot_line(row, label, formula, big=False, fmt=FMT_USD):
    inv.merge_cells(start_row=row, start_column=7, end_row=row, end_column=9)
    inv.cell(row, 7).value = label
    inv.cell(row, 7).font = font(size=11 if not big else 14, bold=True, color=WHITE if big else DARK)
    inv.cell(row, 7).alignment = right()
    if big:
        inv.cell(row, 7).fill = fill(NAVY)
    inv.cell(row, 10).value = formula
    inv.cell(row, 10).font = font(size=11 if not big else 14, bold=True, color=WHITE if big else NAVY)
    inv.cell(row, 10).alignment = right()
    inv.cell(row, 10).number_format = fmt
    if big:
        inv.cell(row, 10).fill = fill(NAVY)
    else:
        inv.cell(row, 10).border = Border(top=Side(style='thin', color=GRAY_RULE))

subtotal_formula = '=SUMIF(Trips[Claim No.],$B$11,Trips[Demurrage (USD)])'
tot_line(tot_start,   'Subtotal',  subtotal_formula)
tot_line(tot_start+1, '="VAT ("&TEXT(VAT_RATE,"0%")&")"', f'={subtotal_formula[1:]}*VAT_RATE')
tot_line(tot_start+3, 'TOTAL DUE', f'=ROUND({subtotal_formula[1:]}*(1+VAT_RATE),2)', big=True, fmt=FMT_USD_DEC)
inv.row_dimensions[tot_start+3].height = 28

# Notes & Payment block
notes_row = tot_start + 6
inv.cell(notes_row, 2).value = 'PAYMENT DETAILS'
inv.cell(notes_row, 2).font = font(size=10, bold=True, color=NAVY)
inv.cell(notes_row, 2).alignment = left()
inv.cell(notes_row, 2).border = Border(bottom=Side(style='thin', color=GOLD))
for c in range(2, 12):
    inv.cell(notes_row, c).border = Border(bottom=Side(style='thin', color=GOLD))

inv.cell(notes_row+1, 2).value = '="Bank:  "&BANK_NAME'
inv.cell(notes_row+2, 2).value = '="Account name:  "&BANK_HOLDER'
inv.cell(notes_row+3, 2).value = '="Account number:  "&BANK_ACCT'
inv.cell(notes_row+1, 7).value = '="IBAN:  "&BANK_IBAN'
inv.cell(notes_row+2, 7).value = '="SWIFT / BIC:  "&BANK_SWIFT'
inv.cell(notes_row+3, 7).value = '="Correspondent:  "&BANK_CORR'
for r in range(notes_row+1, notes_row+4):
    for col in (2, 7):
        inv.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col+4)
        inv.cell(r, col).font = font(size=10, color=DARK)
        inv.cell(r, col).alignment = left()

# Payment terms / footer
foot_row = notes_row + 5
inv.merge_cells(start_row=foot_row, start_column=2, end_row=foot_row, end_column=11)
inv.cell(foot_row, 2).value = ('="Payment terms: Net "&PAY_TERMS&" days from invoice date — please quote invoice number on remittance.   "&INV_FOOTER')
inv.cell(foot_row, 2).font = font(size=9, italic=True, color=MUTED)
inv.cell(foot_row, 2).alignment = left(wrap=True)
inv.row_dimensions[foot_row].height = 28

# Signature block
sig_row = foot_row + 3
inv.cell(sig_row, 2).value = 'Authorised signatory'
inv.cell(sig_row, 2).font = font(size=9, color=MUTED)
inv.cell(sig_row+1, 2).value = '____________________________'
inv.cell(sig_row+1, 2).font = font(size=11, color=DARK)
inv.cell(sig_row, 8).value = 'Date'
inv.cell(sig_row, 8).font = font(size=9, color=MUTED)
inv.cell(sig_row+1, 8).value = '____________________________'
inv.cell(sig_row+1, 8).font = font(size=11, color=DARK)

# Print setup: one page if possible
inv.page_setup.orientation = inv.ORIENTATION_PORTRAIT
inv.page_setup.fitToWidth = 1
inv.page_setup.fitToHeight = 1
inv.sheet_properties.pageSetUpPr.fitToPage = True
inv.print_options.horizontalCentered = True
inv.print_area = f'A1:L{sig_row+2}'
inv.page_margins.left = 0.5
inv.page_margins.right = 0.5
inv.page_margins.top = 0.5
inv.page_margins.bottom = 0.5

# ============================================================
# 8. DASHBOARD
# ============================================================
dash = wb.create_sheet('Dashboard')
dash.sheet_view.showGridLines = False
dash.sheet_view.showRowColHeaders = False

widths = {'A':2, 'B':22,'C':22,'D':22,'E':22,'F':22,'G':22,'H':22,'I':22, 'J':2}
for col, w in widths.items():
    dash.column_dimensions[col].width = w

dash.merge_cells('B2:I2')
dash.cell(2,2).value = 'DEMURRAGE DASHBOARD'
dash.cell(2,2).font = font(size=24, bold=True, color=NAVY)
dash.cell(2,2).alignment = left()
dash.row_dimensions[2].height = 36

dash.merge_cells('B3:I3')
dash.cell(3,2).value = 'Live KPIs across trips, claims and invoices.'
dash.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 10):
    dash.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))
dash.row_dimensions[4].height = 6

def dash_kpi(row, col, label, formula, fmt=FMT_USD):
    dash.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col+1)
    dash.cell(row, col).value = label
    dash.cell(row, col).font = font(size=10, bold=True, color=WHITE)
    dash.cell(row, col).fill = fill(NAVY_MID)
    dash.cell(row, col).alignment = center()
    dash.row_dimensions[row].height = 22
    dash.merge_cells(start_row=row+1, start_column=col, end_row=row+2, end_column=col+1)
    c = dash.cell(row+1, col)
    c.value = formula
    c.font = font(size=20, bold=True, color=NAVY)
    c.fill = fill(WHITE)
    c.alignment = center()
    c.number_format = fmt
    for rr in range(row, row+3):
        for cc in range(col, col+2):
            dash.cell(rr, cc).border = Border(
                left=Side(style='thin', color=GOLD), right=Side(style='thin', color=GOLD),
                top=Side(style='thin', color=GOLD), bottom=Side(style='thin', color=GOLD))

# Row 1 of KPIs — operational
dash_kpi(6, 2, 'TOTAL DEMURRAGE',  '=SUM(Trips[Demurrage (USD)])', FMT_USD)
dash_kpi(6, 4, 'TRIPS',            '=ROWS(Trips[Deal No.])',       FMT_INT)
dash_kpi(6, 6, 'IN DEMURRAGE',     '=COUNTIF(Trips[Status],"DEMURRAGE")', FMT_INT)
dash_kpi(6, 8, 'AVG / TRIP',       '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)', FMT_USD)

# Row 2 — commercial
dash_kpi(10, 2, 'INVOICED',     '=SUMIFS(Claims[Amount (USD)],Claims[Status],"Sent")+SUMIFS(Claims[Amount (USD)],Claims[Status],"Paid")', FMT_USD)
dash_kpi(10, 4, 'PAID',         '=SUMIF(Claims[Status],"Paid",Claims[Amount (USD)])', FMT_USD)
dash_kpi(10, 6, 'OUTSTANDING',  '=SUMIF(Claims[Status],"Sent",Claims[Amount (USD)])', FMT_USD)
dash_kpi(10, 8, 'OVERDUE',      '=SUMIFS(Claims[Amount (USD)],Claims[Status],"Sent",Claims[Days Overdue],">0")', FMT_USD)

# === Breakdown table helper ===
def breakdown(start_row, col_start, title, headers, rows_data):
    span = len(headers)
    end_col = col_start + span - 1
    dash.merge_cells(start_row=start_row, start_column=col_start, end_row=start_row, end_column=end_col)
    c = dash.cell(start_row, col_start)
    c.value = title; c.font = font(size=12, bold=True, color=WHITE); c.fill = fill(NAVY)
    c.alignment = left(indent=1)
    dash.row_dimensions[start_row].height = 24
    hr = start_row + 1
    for i, h in enumerate(headers):
        cc = dash.cell(hr, col_start+i)
        cc.value = h
        cc.font = font(size=10, bold=True, color=NAVY)
        cc.fill = fill(GOLD_PALE)
        cc.alignment = center() if i>0 else left(indent=1)
        cc.border = Border(left=thin, right=thin, top=thin, bottom=Side(style='medium', color=GOLD))
    dash.row_dimensions[hr].height = 22
    for i, rd in enumerate(rows_data):
        r = hr + 1 + i
        for j, v in enumerate(rd):
            cc = dash.cell(r, col_start+j)
            cc.value = v
            cc.font = font(size=10)
            cc.alignment = left(indent=1) if j==0 else right()
            cc.border = Border(left=thin, right=thin,
                              top=Side(style='dotted', color=GRAY_RULE),
                              bottom=Side(style='dotted', color=GRAY_RULE))
            if i % 2 == 1: cc.fill = fill(CREAM)
        dash.cell(r, col_start+1).number_format = FMT_INT
        if span >= 3: dash.cell(r, col_start+2).number_format = FMT_USD
        if span >= 4: dash.cell(r, col_start+3).number_format = FMT_USD
    tr = hr + 1 + len(rows_data)
    for j in range(span):
        cc = dash.cell(tr, col_start+j)
        cc.font = font(size=10, bold=True, color=WHITE); cc.fill = fill(NAVY)
        cc.alignment = left(indent=1) if j==0 else right()
        cc.border = Border(top=Side(style='medium', color=GOLD))
    dash.cell(tr, col_start).value = 'TOTAL'
    return tr

# By consignee
consignees = sorted(set(d['consignee'] for d in deals if d['consignee']))
rows_c = [[
    cn,
    f'=COUNTIF(Trips[Consignee],"{cn}")',
    f'=SUMIF(Trips[Consignee],"{cn}",Trips[Demurrage (USD)])',
    f'=IFERROR(SUMIF(Trips[Consignee],"{cn}",Trips[Demurrage (USD)])/COUNTIF(Trips[Consignee],"{cn}"),0)',
] for cn in consignees]
end_c = breakdown(14, 2, 'BY CONSIGNEE',
                  ['Consignee', 'Trips', 'Total Demurrage', 'Avg / Trip'], rows_c)
dash.cell(end_c, 3).value = '=ROWS(Trips[Deal No.])'; dash.cell(end_c, 3).number_format = FMT_INT
dash.cell(end_c, 4).value = '=SUM(Trips[Demurrage (USD)])'; dash.cell(end_c, 4).number_format = FMT_USD
dash.cell(end_c, 5).value = '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)'; dash.cell(end_c, 5).number_format = FMT_USD

# By transporter
transporters = sorted(set(t['transporter'] for t in trips if t['transporter']))
rows_t = [[
    tr,
    f'=COUNTIF(Trips[Transporter],"{tr}")',
    f'=SUMIF(Trips[Transporter],"{tr}",Trips[Demurrage (USD)])',
    f'=IFERROR(SUMIF(Trips[Transporter],"{tr}",Trips[Demurrage (USD)])/COUNTIF(Trips[Transporter],"{tr}"),0)',
] for tr in transporters]
start_t = end_c + 3
end_t = breakdown(start_t, 2, 'BY TRANSPORTER',
                  ['Transporter', 'Trips', 'Total Demurrage', 'Avg / Trip'], rows_t)
dash.cell(end_t, 3).value = '=ROWS(Trips[Deal No.])'; dash.cell(end_t, 3).number_format = FMT_INT
dash.cell(end_t, 4).value = '=SUM(Trips[Demurrage (USD)])'; dash.cell(end_t, 4).number_format = FMT_USD
dash.cell(end_t, 5).value = '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)'; dash.cell(end_t, 5).number_format = FMT_USD

# By month
months = sorted({t['date_loaded'].strftime('%Y-%m') for t in trips if t['date_loaded']})
rows_m = [[
    m,
    f'=COUNTIF(Trips[Month],"{m}")',
    f'=SUMIF(Trips[Month],"{m}",Trips[Demurrage (USD)])',
    f'=IFERROR(SUMIF(Trips[Month],"{m}",Trips[Demurrage (USD)])/COUNTIF(Trips[Month],"{m}"),0)',
] for m in months]
start_m = end_t + 3
end_m = breakdown(start_m, 2, 'BY MONTH (LOADING)',
                  ['Month', 'Trips', 'Total Demurrage', 'Avg / Trip'], rows_m)
dash.cell(end_m, 3).value = '=ROWS(Trips[Deal No.])'; dash.cell(end_m, 3).number_format = FMT_INT
dash.cell(end_m, 4).value = '=SUM(Trips[Demurrage (USD)])'; dash.cell(end_m, 4).number_format = FMT_USD
dash.cell(end_m, 5).value = '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)'; dash.cell(end_m, 5).number_format = FMT_USD

# Top deals
deal_totals = {}
for t in trips:
    deal_totals[t['deal']] = deal_totals.get(t['deal'], 0) + (t['demurrage'] or 0)
top_deals = sorted(deal_totals.items(), key=lambda x: -x[1])[:10]
rows_top = [[
    d,
    f'=COUNTIF(Trips[Deal No.],{d})',
    f'=SUMIF(Trips[Deal No.],{d},Trips[Demurrage (USD)])',
    f'=IFERROR(SUMIF(Trips[Deal No.],{d},Trips[Demurrage (USD)])/COUNTIF(Trips[Deal No.],{d}),0)',
] for d, _ in top_deals]
end_top = breakdown(14, 6, 'TOP DEALS BY DEMURRAGE',
                    ['Deal No.', 'Trips', 'Total Demurrage', 'Avg / Trip'], rows_top)
dash.cell(end_top, 7).value = f'=SUM(G16:G{end_top-1})'; dash.cell(end_top, 7).number_format = FMT_INT
dash.cell(end_top, 8).value = f'=SUM(H16:H{end_top-1})'; dash.cell(end_top, 8).number_format = FMT_USD
dash.cell(end_top, 9).value = f'=IFERROR(H{end_top}/G{end_top},0)'; dash.cell(end_top, 9).number_format = FMT_USD

# === CLAIMS AGING table ===
aging_rows = [
    ['Current (not yet due)', '=COUNTIF(Claims[Aging],"Current")', '=SUMIF(Claims[Aging],"Current",Claims[Amount (USD)])'],
    ['1–30 days overdue',     '=COUNTIF(Claims[Aging],"1-30")',   '=SUMIF(Claims[Aging],"1-30",Claims[Amount (USD)])'],
    ['31–60 days overdue',    '=COUNTIF(Claims[Aging],"31-60")',  '=SUMIF(Claims[Aging],"31-60",Claims[Amount (USD)])'],
    ['60+ days overdue',      '=COUNTIF(Claims[Aging],"60+")',    '=SUMIF(Claims[Aging],"60+",Claims[Amount (USD)])'],
    ['Paid',                  '=COUNTIF(Claims[Aging],"Paid")',   '=SUMIF(Claims[Aging],"Paid",Claims[Amount (USD)])'],
]
start_age = end_top + 3
end_age = breakdown(start_age, 6, 'CLAIMS AGING',
                    ['Bucket', 'Claims', 'Amount'], aging_rows)
dash.cell(end_age, 7).value = '=ROWS(Claims[Claim No.])'; dash.cell(end_age, 7).number_format = FMT_INT
dash.cell(end_age, 8).value = '=SUM(Claims[Amount (USD)])'; dash.cell(end_age, 8).number_format = FMT_USD

dash.freeze_panes = 'B6'

# ============================================================
# Tab order & colors
# ============================================================
order = ['Cover','Dashboard','Invoice','Claims','Trips Ledger','Deals','Assumptions','Company']
wb._sheets = [wb[s] for s in order]

color_map = {
    'Cover': NAVY,
    'Dashboard': GOLD,
    'Invoice': GOLD,
    'Claims': GOLD,
    'Trips Ledger': NAVY_MID,
    'Deals': NAVY_MID,
    'Assumptions': MUTED,
    'Company': MUTED,
}
for s, c in color_map.items():
    wb[s].sheet_properties.tabColor = c

wb.active = 0

out = '/home/user/test/DEMURRAGE_TRUCKING_2026_v3.xlsx'
wb.save(out)
print('Saved:', out)
import os
print('Size:', os.path.getsize(out), 'bytes')
print(f'Sheets: {wb.sheetnames}')
print(f'Claims pre-built: {len(claims)}')
print(f'Trips: {len(trips)} — total demurrage: ${sum((t["demurrage"] or 0) for t in trips):,}')
