"""Build the all-in-one MOCOH demurrage workbook (v4).

Fixes from v3:
- Waiting-days formula: was referencing wrong columns (Driver instead of
  Arrival); now correctly Offloaded - Arrival.
- Line-item lookups: replaced INDEX/SMALL/IF (legacy array — needed CSE)
  with AGGREGATE (Excel 2010+, no CSE).
- Invoice tab rebuilt to MOCOH letterhead format with embedded
  logo, signature and stamp.
- Company defaults populated with MOCOH SA Geneva details.
- Print areas set correctly.
"""
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
from openpyxl.drawing.image import Image as XLImage

with open('/tmp/data.pkl','rb') as f:
    data = pickle.load(f)
deals = data['deals']
trips = data['trips']

# Normalize
for t in trips:
    t['transporter'] = (t['transporter'] or '').strip().upper() or None
    t['consignee'] = (t['consignee'] or '').strip()

# === Palette ===
# MOCOH brand: orange leopard + navy "mocoh" wordmark
MOCOH_NAVY = '1F3D8E'     # navy from logo
MOCOH_ORANGE = 'F5A623'   # orange leopard
NAVY = '0B2447'
NAVY_MID = '19376D'
GOLD = 'C9A227'
GOLD_LIGHT = 'F4E1A4'
GOLD_PALE = 'FDF4D4'
CREAM = 'FDFBF7'
GRAY_RULE = 'E5E7EB'
GRAY_HEADER = 'F3F4F6'
RED_BG = 'FCE4E4'; RED_FG = '991B1B'
GREEN_BG = 'DCFCE7'; GREEN_FG = '166534'
AMBER_BG = 'FEF3C7'; AMBER_FG = '92400E'
WHITE = 'FFFFFF'; DARK = '111827'; MUTED = '6B7280'

thin = Side(style='thin', color=GRAY_RULE)
medium_gold = Side(style='medium', color=GOLD)
medium_navy = Side(style='medium', color=MOCOH_NAVY)
border_all = Border(left=thin, right=thin, top=thin, bottom=thin)

def font(size=11, bold=False, color=DARK, italic=False, name='Calibri'):
    return Font(name=name, size=size, bold=bold, color=color, italic=italic)
def fill(c): return PatternFill('solid', fgColor=c)
def center(wrap=False): return Alignment(horizontal='center', vertical='center', wrap_text=wrap)
def left(wrap=False, indent=0): return Alignment(horizontal='left', vertical='center', wrap_text=wrap, indent=indent)
def right(wrap=False, indent=0): return Alignment(horizontal='right', vertical='center', wrap_text=wrap, indent=indent)

FMT_USD = '_-[$$-409]* #,##0_-;[Red]-[$$-409]* #,##0_-;_-[$$-409]* "-"??_-;_-@_-'
FMT_USD_DEC = '_-[$$-409]* #,##0.00_-;[Red]-[$$-409]* #,##0.00_-'
FMT_INT = '#,##0;[Red]-#,##0;"-"'
FMT_DATE = 'dd-mmm-yyyy'
FMT_PCT = '0.0%'

wb = Workbook()
wb.remove(wb.active)

# ========== Pre-compute sample claims from existing trips ==========
deal_trips = defaultdict(list)
for t in trips:
    deal_trips[t['deal']].append(t)

claims = []
claim_no_by_deal = {}
for i, (deal_no, ts) in enumerate(sorted(deal_trips.items()), start=1):
    cn = f'MOC-DEM-2026-{i:03d}'
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
        'bill_to': '[Plot / Street]\n[City], [Country]\n[VAT / TIN]',
        'period_from': cmin,
        'period_to': cmax,
        'status': 'Draft',
        'paid_date': None,
        'notes': f'Demurrage on Deal {deal_no} — {deal_meta.get("route","")}',
    })
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
        cover.cell(r, c).fill = fill(MOCOH_NAVY)

cover.merge_cells('B3:I4')
cover.cell(3,2).value = 'DEMURRAGE MANAGEMENT'
cover.cell(3,2).font = font(size=32, bold=True, color=WHITE)
cover.cell(3,2).alignment = Alignment(horizontal='left', vertical='center')

cover.merge_cells('B5:I5')
cover.cell(5,2).value = 'MOCOH SA  •  TRUCKING DEMURRAGE  •  2026'
cover.cell(5,2).font = font(size=12, bold=True, color=MOCOH_ORANGE)
cover.cell(5,2).alignment = Alignment(horizontal='left', vertical='center')

for c in range(1, 11):
    cover.cell(7, c).fill = fill(MOCOH_ORANGE)
cover.row_dimensions[7].height = 4

# Workflow stepper
cover.cell(10,2).value = 'WORKFLOW'
cover.cell(10,2).font = font(size=12, bold=True, color=MOCOH_NAVY)

steps = [
    ('1', 'CAPTURE', 'Add trips to the Trips Ledger as they happen.'),
    ('2', 'CLAIM',   'Open the Claims register, add a row, assign trips.'),
    ('3', 'INVOICE', 'Pick the claim on the Invoice tab — print or PDF.'),
    ('4', 'TRACK',   'Update status / paid date — Dashboard reflects it.'),
]
row = 12
for n, title, desc in steps:
    cover.cell(row, 2).value = n
    cover.cell(row, 2).font = font(size=18, bold=True, color=WHITE)
    cover.cell(row, 2).fill = fill(MOCOH_ORANGE)
    cover.cell(row, 2).alignment = center()
    cover.cell(row, 2).border = border_all
    cover.merge_cells(start_row=row, start_column=3, end_row=row, end_column=9)
    cover.cell(row, 3).value = f'{title}  —  {desc}'
    cover.cell(row, 3).font = font(size=12, color=DARK)
    cover.cell(row, 3).alignment = left(indent=1)
    cover.cell(row, 3).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    cover.row_dimensions[row].height = 30
    row += 1

# KPI cards
cover.cell(22, 2).value = 'PORTFOLIO AT A GLANCE'
cover.cell(22, 2).font = font(size=12, bold=True, color=MOCOH_NAVY)

def kpi(row, col_start, label, value_formula, fmt):
    cover.merge_cells(start_row=row, start_column=col_start, end_row=row, end_column=col_start+1)
    cover.merge_cells(start_row=row+1, start_column=col_start, end_row=row+2, end_column=col_start+1)
    cover.cell(row, col_start).value = label
    cover.cell(row, col_start).font = font(size=9, bold=True, color=WHITE)
    cover.cell(row, col_start).alignment = center()
    cover.cell(row, col_start).fill = fill(MOCOH_NAVY)
    v = cover.cell(row+1, col_start)
    v.value = value_formula
    v.font = font(size=18, bold=True, color=MOCOH_NAVY)
    v.alignment = center()
    v.fill = fill(CREAM)
    v.number_format = fmt
    for rr in range(row, row+3):
        for cc in range(col_start, col_start+2):
            cover.cell(rr, cc).border = Border(
                left=Side(style='thin', color=MOCOH_ORANGE), right=Side(style='thin', color=MOCOH_ORANGE),
                top=Side(style='thin', color=MOCOH_ORANGE), bottom=Side(style='thin', color=MOCOH_ORANGE))

kpi(24, 2, 'TOTAL DEMURRAGE', '=SUM(Trips[Demurrage (USD)])', FMT_USD)
kpi(24, 4, 'INVOICED',
    '=SUMIFS(Claims[Amount (USD)],Claims[Status],"Sent")+SUMIFS(Claims[Amount (USD)],Claims[Status],"Paid")',
    FMT_USD)
kpi(24, 6, 'PAID',
    '=SUMIF(Claims[Status],"Paid",Claims[Amount (USD)])', FMT_USD)
kpi(24, 8, 'OUTSTANDING',
    '=SUMIF(Claims[Status],"Sent",Claims[Amount (USD)])', FMT_USD)

cover.merge_cells('B36:I36')
cover.cell(36, 2).value = 'CONFIDENTIAL  •  MOCOH SA  •  Internal use only'
cover.cell(36, 2).font = font(size=9, italic=True, color=MUTED)
cover.cell(36, 2).alignment = center()

# ============================================================
# 2. COMPANY (with MOCOH defaults)
# ============================================================
co = wb.create_sheet('Company')
co.sheet_view.showGridLines = False
co.column_dimensions['A'].width = 2
co.column_dimensions['B'].width = 34
co.column_dimensions['C'].width = 55
co.column_dimensions['D'].width = 40

co.merge_cells('B2:D2')
co.cell(2,2).value = 'COMPANY & INVOICING DETAILS'
co.cell(2,2).font = font(size=20, bold=True, color=MOCOH_NAVY)
co.row_dimensions[2].height = 32

co.merge_cells('B3:D3')
co.cell(3,2).value = 'Set once. Everything in invoices is pulled from here.'
co.cell(3,2).font = font(size=10, italic=True, color=MUTED)

for c in range(2, 5):
    co.cell(4, c).border = Border(top=Side(style='medium', color=MOCOH_ORANGE))

def co_section(row, title):
    co.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    co.cell(row,2).value = title
    co.cell(row,2).font = font(size=11, bold=True, color=WHITE)
    co.cell(row,2).fill = fill(MOCOH_NAVY)
    co.cell(row,2).alignment = left(indent=1)
    co.row_dimensions[row].height = 22

def co_row(row, label, value, fmt=None, wrap=False):
    co.cell(row, 2).value = label
    co.cell(row, 2).font = font(size=11, color=DARK)
    co.cell(row, 2).alignment = left(indent=1)
    co.cell(row, 2).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    c = co.cell(row, 3)
    c.value = value
    c.font = font(size=11, bold=True, color=MOCOH_NAVY)
    c.alignment = left(indent=1, wrap=wrap)
    c.fill = fill(GOLD_PALE)
    c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    if fmt: c.number_format = fmt
    co.row_dimensions[row].height = 22

co_section(6, 'COMPANY (issuer)')
co_row(7,  'Legal name',          'MOCOH SA')
co_row(8,  'Trading name',        'MOCOHSA')
co_row(9,  'Address',             'Rue de la Corraterie 5-7, 1204 Geneva, Switzerland', wrap=True)
co.row_dimensions[9].height = 36
co_row(10, 'VAT / TIN / Reg.',    'CHE-110.540.819')
co_row(11, 'Phone',               '+41 22 000 0000')
co_row(12, 'Email',               'invoicing@mocoh.com')

co_section(14, 'BANK DETAILS (USD)')
co_row(15, 'Beneficiary bank',    'BANQUE INTERNATIONALE DE COMMERCE - BRED (SUISSE) SA')
co_row(16, 'Account name',        'MOCOHSA')
co_row(17, 'IBAN',                'CH79 0853 7603 0748 0040 0')
co_row(18, 'SWIFT / BIC',         'BICFCHGGXXX')
co_row(19, 'Correspondent bank',  'JP MORGAN CHASE NY')
co_row(20, 'Correspondent SWIFT', 'CHASUS33XXX')

co_section(22, 'INVOICING')
co_row(23, 'Invoice prefix',       'MOC-DEM-2026-')
co_row(24, 'Next invoice number',  1, fmt=FMT_INT)
co_row(25, 'Payment terms (days)', 14, fmt=FMT_INT)
co_row(26, 'VAT rate',             0, fmt=FMT_PCT)
co_row(27, 'Footer note',
       'Payment with liberating effect can only be made to this account held with the above mentioned bank, '
       'as assignee of the proceeds. Open account payable as per agreed terms.',
       wrap=True)
co.row_dimensions[27].height = 56

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
nm['BANK_IBAN']       = DefinedName('BANK_IBAN',       attr_text="Company!$C$17")
nm['BANK_SWIFT']      = DefinedName('BANK_SWIFT',      attr_text="Company!$C$18")
nm['BANK_CORR']       = DefinedName('BANK_CORR',       attr_text="Company!$C$19")
nm['BANK_CORR_SWIFT'] = DefinedName('BANK_CORR_SWIFT', attr_text="Company!$C$20")
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
asm.cell(2,2).font = font(size=20, bold=True, color=MOCOH_NAVY)
asm.row_dimensions[2].height = 32
asm.merge_cells('B3:D3')
asm.cell(3,2).value = 'Edit gold cells to update the entire workbook.'
asm.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 5):
    asm.cell(4, c).border = Border(top=Side(style='medium', color=MOCOH_ORANGE))

def asm_section(row, title):
    asm.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    asm.cell(row,2).value = title
    asm.cell(row,2).font = font(size=11, bold=True, color=WHITE)
    asm.cell(row,2).fill = fill(MOCOH_NAVY)
    asm.cell(row,2).alignment = left(indent=1)
    asm.row_dimensions[row].height = 22

def asm_row(row, label, value, note='', fmt=None):
    asm.cell(row, 2).value = label
    asm.cell(row, 2).font = font(size=11)
    asm.cell(row, 2).alignment = left(indent=1)
    asm.cell(row, 2).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    c = asm.cell(row, 3)
    c.value = value
    c.font = font(size=11, bold=True, color=MOCOH_NAVY)
    c.alignment = center()
    c.fill = fill(GOLD_PALE)
    c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    if fmt: c.number_format = fmt
    asm.cell(row, 4).value = note
    asm.cell(row, 4).font = font(size=10, italic=True, color=MUTED)
    asm.cell(row, 4).alignment = left(indent=1)
    asm.row_dimensions[row].height = 20

asm_section(6, 'COMMERCIAL DEFAULTS')
asm_row(7,  'Default laytime (days)',           2,    'Free time at offloading before demurrage accrues.')
asm_row(8,  'Default demurrage rate (USD/day)', 250,  'Per-truck per-day charge once laytime exceeded.')
asm_row(9,  'Currency',                         'USD','Reporting currency.')
asm_row(10, 'FX rate (local → USD)',            1.00, '1.00 if invoices already in USD.', fmt='0.0000')

asm_section(12, 'REPORTING PERIOD')
asm_row(13, 'Period start',   datetime(2026,1,1),  'Inclusive.', fmt=FMT_DATE)
asm_row(14, 'Period end',     datetime(2026,4,30), 'Inclusive.', fmt=FMT_DATE)
asm_row(15, 'Report issued',  datetime(2026,5,15), '',           fmt=FMT_DATE)

asm_section(17, 'TOLERANCES & FLAGS')
asm_row(18, 'Outlier threshold (waiting days)', 7, 'Trips above this are highlighted.')
asm_row(19, 'Sanity tolerance (days)', 0, 'Days of grace before flagging.')

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
dm.cell(2,2).font = font(size=20, bold=True, color=MOCOH_NAVY)
dm.row_dimensions[2].height = 32
dm.merge_cells('B3:K3')
dm.cell(3,2).value = 'Register of all demurrage deals.'
dm.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 12):
    dm.cell(4, c).border = Border(top=Side(style='medium', color=MOCOH_ORANGE))

headers_dm = ['Deal No.','Consignee','Route','Loading Port','Destination','Product',
              'Laytime (days)','Rate (USD/day)','Transport (USD/m³)','Transporter']
hr = 6
for i, h in enumerate(headers_dm):
    c = dm.cell(hr, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(MOCOH_NAVY)
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
# 5. TRIPS LEDGER  — with FIX on Waiting formula
# ============================================================
tl = wb.create_sheet('Trips Ledger')
tl.sheet_view.showGridLines = False

trip_cols = [
    ('Deal No.', 10), ('Claim No.', 16), ('Consignee', 22), ('Date Loaded', 13),
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
tl.cell(2,2).font = font(size=20, bold=True, color=MOCOH_NAVY)
tl.row_dimensions[2].height = 32

tl.merge_cells(f'B3:{last_col_letter}3')
tl.cell(3,2).value = ('All truck movements. Assign a Claim No. to bundle trips into a claim. '
                     'New rows added at the bottom inherit formulas automatically.')
tl.cell(3,2).font = font(size=10, italic=True, color=MUTED)

for c in range(2, 2+len(trip_cols)):
    tl.cell(4, c).border = Border(top=Side(style='medium', color=MOCOH_ORANGE))

hr = 6
for i, (h, _) in enumerate(trip_cols):
    c = tl.cell(hr, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(MOCOH_NAVY)
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
    # WAITING = Offloaded(N) - Arrival(M)   ← bug fixed (was referencing L,M)
    tl.cell(r,15).value = f'=IF(OR(M{r}="",N{r}=""),"",N{r}-M{r})'
    tl.cell(r,16).value = f'=IFERROR(VLOOKUP(B{r},Deals[#All],7,FALSE),DEF_LAYTIME)'
    tl.cell(r,17).value = f'=IF(O{r}="","",MAX(0,O{r}-P{r}))'
    tl.cell(r,18).value = f'=IFERROR(VLOOKUP(B{r},Deals[#All],8,FALSE),DEF_RATE)'
    tl.cell(r,19).value = f'=IF(Q{r}="","",Q{r}*R{r})'
    tl.cell(r,20).value = f'=IF(O{r}="","PENDING",IF(Q{r}>0,"DEMURRAGE","ON-TIME"))'
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
    tl.cell(r, 2).alignment = center()
    tl.cell(r, 3).alignment = center()
    tl.cell(r, 5).number_format = FMT_DATE; tl.cell(r, 5).alignment = center()
    tl.cell(r,13).number_format = FMT_DATE; tl.cell(r,13).alignment = center()
    tl.cell(r,14).number_format = FMT_DATE; tl.cell(r,14).alignment = center()
    for col in (15,16,17):
        tl.cell(r,col).number_format = FMT_INT
        tl.cell(r,col).alignment = center()
    tl.cell(r,18).number_format = FMT_USD; tl.cell(r,18).alignment = right()
    tl.cell(r,19).number_format = FMT_USD; tl.cell(r,19).alignment = right()
    for col in (20,21,22):
        tl.cell(r,col).alignment = center()

trip_ref = f'B{hr}:{last_col_letter}{last_row}'
tt = Table(displayName='Trips', ref=trip_ref)
tt.tableStyleInfo = TableStyleInfo(name='TableStyleLight1', showRowStripes=True, showColumnStripes=False)
tl.add_table(tt)

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

dv_claim = DataValidation(type='list', formula1='=Claims[Claim No.]', allow_blank=True)
dv_claim.add(f'C{hr+1}:C{hr+500}')
tl.add_data_validation(dv_claim)

# Totals
tot = last_row + 2
for j in range(2, 2+len(trip_cols)):
    tl.cell(tot, j).fill = fill(MOCOH_NAVY)
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
    ('Claim No.', 18), ('Issue Date', 13), ('Deal No.', 11),
    ('Consignee', 26), ('Bill-To Address', 36),
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
cl.cell(2,2).font = font(size=20, bold=True, color=MOCOH_NAVY)
cl.row_dimensions[2].height = 32
cl.merge_cells(f'B3:{last_col_cl}3')
cl.cell(3,2).value = ('One row per claim. Assign trips to the Claim No. on the Trips Ledger; '
                     'then preview / print on the Invoice tab.')
cl.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 2+len(cl_cols)):
    cl.cell(4, c).border = Border(top=Side(style='medium', color=MOCOH_ORANGE))

hr = 6
for i, (h, _) in enumerate(cl_cols):
    c = cl.cell(hr, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(MOCOH_NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
cl.row_dimensions[hr].height = 36

# Cols: B=Claim C=Issue D=Deal E=Consignee F=BillTo G=From H=To
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
    cl.cell(r,15).value = f'=IF(L{r}="Paid",0,IF(L{r}="Sent",MAX(0,TODAY()-M{r}),""))'
    cl.cell(r,16).value = (f'=IF(L{r}="Paid","Paid",'
                          f'IF(L{r}<>"Sent","",'
                          f'IF(ISNUMBER(O{r}),'
                          f'IF(O{r}<=0,"Current",IF(O{r}<=30,"1-30",IF(O{r}<=60,"31-60","60+"))),'
                          f'"")))')
    cl.cell(r,17).value = cm['notes']

last_row_cl = hr + len(claims)

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

claim_ref = f'B{hr}:{last_col_cl}{last_row_cl}'
tt2 = Table(displayName='Claims', ref=claim_ref)
tt2.tableStyleInfo = TableStyleInfo(name='TableStyleLight1', showRowStripes=True)
cl.add_table(tt2)

dv_status = DataValidation(type='list', formula1='"Draft,Sent,Paid,Cancelled"', allow_blank=False)
dv_status.add(f'L{hr+1}:L{hr+500}')
cl.add_data_validation(dv_status)

status_rng = f'L{hr+1}:L{last_row_cl}'
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Paid"'], fill=fill(GREEN_BG), font=font(bold=True, color=GREEN_FG)))
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Sent"'], fill=fill(AMBER_BG), font=font(bold=True, color=AMBER_FG)))
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Draft"'], fill=fill(GOLD_PALE), font=font(bold=True, color=MOCOH_NAVY)))
cl.conditional_formatting.add(status_rng,
    CellIsRule(operator='equal', formula=['"Cancelled"'], fill=fill(GRAY_HEADER), font=font(italic=True, color=MUTED)))

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
    cl.cell(tot, j).fill = fill(MOCOH_NAVY); cl.cell(tot, j).font = font(bold=True, color=WHITE)
cl.cell(tot, 2).value = 'TOTAL'; cl.cell(tot, 2).alignment = center()
cl.cell(tot, 9).value = '=SUBTOTAL(109,Claims[# Trips])'; cl.cell(tot,9).number_format=FMT_INT; cl.cell(tot,9).alignment=center()
cl.cell(tot,10).value = '=SUBTOTAL(109,Claims[Amount (USD)])'; cl.cell(tot,10).number_format=FMT_USD; cl.cell(tot,10).alignment=right()

cl.freeze_panes = f'C{hr+1}'
cl.page_setup.orientation = cl.ORIENTATION_LANDSCAPE
cl.page_setup.fitToWidth = 1
cl.sheet_properties.pageSetUpPr.fitToPage = True

# ============================================================
# 7. INVOICE  —  MOCOH letterhead format
# ============================================================
inv = wb.create_sheet('Invoice')
inv.sheet_view.showGridLines = False
inv.sheet_view.showRowColHeaders = False

# A4 portrait body — use ~10 narrower columns to fit page width
# A is left margin, K right margin
widths = {'A':2, 'B':11, 'C':11, 'D':11, 'E':11, 'F':11, 'G':11, 'H':11, 'I':11, 'J':11, 'K':2}
for col, w in widths.items():
    inv.column_dimensions[col].width = w

# Page setup
inv.page_setup.orientation = inv.ORIENTATION_PORTRAIT
inv.page_setup.paperSize = inv.PAPERSIZE_A4
inv.page_setup.fitToWidth = 1
inv.page_setup.fitToHeight = 1
inv.sheet_properties.pageSetUpPr.fitToPage = True
inv.print_options.horizontalCentered = True
inv.page_margins.left = 0.5
inv.page_margins.right = 0.5
inv.page_margins.top = 0.4
inv.page_margins.bottom = 0.4

# Top area: rows 1-6 reserved for logo on the left, title on the right
for r in range(1, 7):
    inv.row_dimensions[r].height = 18

# Big title on right
inv.merge_cells('F2:J2')
inv.cell(2, 6).value = 'DEMURRAGE INVOICE'
inv.cell(2, 6).font = font(size=22, bold=True, color=MOCOH_NAVY)
inv.cell(2, 6).alignment = right()

# Subline
inv.merge_cells('F3:J3')
inv.cell(3, 6).value = '=COMPANY_TRADING'
inv.cell(3, 6).font = font(size=10, italic=True, color=MUTED)
inv.cell(3, 6).alignment = right()

# Orange separator
for c in range(2, 11):
    inv.cell(7, c).border = Border(bottom=Side(style='medium', color=MOCOH_ORANGE))
inv.row_dimensions[7].height = 6

# Embed MOCOH logo top-left  (image at /home/user/test/assets/mocoh_logo.jpeg, 608x288 → fit ~140×66 px)
try:
    img = XLImage('/home/user/test/assets/mocoh_logo.jpeg')
    img.height = 70
    img.width = 150
    inv.add_image(img, 'B2')
except FileNotFoundError:
    pass

# === FROM / TO blocks ===
# Row 9: "FROM" / "TO" labels
inv.cell(9, 2).value = 'FROM:'
inv.cell(9, 2).font = font(size=9, bold=True, color=MUTED)
inv.cell(9, 6).value = 'TO:'
inv.cell(9, 6).font = font(size=9, bold=True, color=MUTED)

# FROM block: company name + address
inv.merge_cells('B10:E10')
inv.cell(10, 2).value = '=COMPANY_NAME'
inv.cell(10, 2).font = font(size=12, bold=True, color=MOCOH_NAVY)
inv.cell(10, 2).alignment = left()

inv.merge_cells('B11:E13')
inv.cell(11, 2).value = '=COMPANY_ADDR'
inv.cell(11, 2).font = font(size=10, color=DARK)
inv.cell(11, 2).alignment = left(wrap=True)
for r in (11, 12, 13):
    inv.row_dimensions[r].height = 14

inv.cell(14, 2).value = '="VAT/Reg.: "&COMPANY_VAT'
inv.cell(14, 2).font = font(size=9, color=MUTED)
inv.cell(14, 2).alignment = left()
inv.merge_cells('B14:E14')

# TO block: consignee name + address from selected claim
inv.merge_cells('F10:J10')
inv.cell(10, 6).value = '=IFERROR(VLOOKUP($B$18,Claims[#All],4,FALSE),"")'
inv.cell(10, 6).font = font(size=12, bold=True, color=MOCOH_NAVY)
inv.cell(10, 6).alignment = left()

inv.merge_cells('F11:J14')
inv.cell(11, 6).value = '=IFERROR(VLOOKUP($B$18,Claims[#All],5,FALSE),"")'
inv.cell(11, 6).font = font(size=10, color=DARK)
inv.cell(11, 6).alignment = left(wrap=True)

# === META row: DATE / INVOICE No. / DEAL REF / PRODUCT ===
# Headers
meta_hdr_row = 16
meta_val_row = 17
meta_cols = [
    (2, 'INVOICE No.', '=INV_PREFIX & TEXT(INV_NEXT + MATCH($B$18, Claims[Claim No.], 0) - 1, "000")', None),
    (4, 'DATE',         '=IFERROR(VLOOKUP($B$18,Claims[#All],2,FALSE),TODAY())', FMT_DATE),
    (6, 'DEAL REF',     '=IFERROR(VLOOKUP($B$18,Claims[#All],3,FALSE),"")', None),
    (8, 'PRODUCT',      '=IFERROR(VLOOKUP(IFERROR(VLOOKUP($B$18,Claims[#All],3,FALSE),0),Deals[#All],6,FALSE),"")', None),
]
for col_start, label, formula, fmt in meta_cols:
    inv.merge_cells(start_row=meta_hdr_row, start_column=col_start, end_row=meta_hdr_row, end_column=col_start+1)
    inv.cell(meta_hdr_row, col_start).value = label
    inv.cell(meta_hdr_row, col_start).font = font(size=9, bold=True, color=WHITE)
    inv.cell(meta_hdr_row, col_start).fill = fill(MOCOH_NAVY)
    inv.cell(meta_hdr_row, col_start).alignment = left(indent=1)

    inv.merge_cells(start_row=meta_val_row, start_column=col_start, end_row=meta_val_row, end_column=col_start+1)
    v = inv.cell(meta_val_row, col_start)
    v.value = formula
    v.font = font(size=12, bold=True, color=MOCOH_NAVY)
    v.fill = fill(CREAM)
    v.alignment = left(indent=1)
    if fmt: v.number_format = fmt
    for rr in (meta_hdr_row, meta_val_row):
        for cc in range(col_start, col_start+2):
            inv.cell(rr, cc).border = Border(
                left=Side(style='thin', color=MOCOH_ORANGE), right=Side(style='thin', color=MOCOH_ORANGE),
                top=Side(style='thin', color=MOCOH_ORANGE), bottom=Side(style='thin', color=MOCOH_ORANGE))
inv.row_dimensions[meta_hdr_row].height = 18
inv.row_dimensions[meta_val_row].height = 22

# === CLAIM picker (gold box) ===
picker_row = 18
inv.cell(picker_row-1, 2).value = ''  # spacer
inv.row_dimensions[picker_row].height = 8

# (intentional: claim picker lives at B18 referenced everywhere above)
# but we want it visible; place it cleanly below the meta row
picker_label_row = 19
picker_box_row = 20
inv.merge_cells(f'B{picker_label_row}:C{picker_label_row}')
inv.cell(picker_label_row, 2).value = 'CLAIM No. (pick from list)'
inv.cell(picker_label_row, 2).font = font(size=9, bold=True, color=MUTED)
inv.cell(picker_label_row, 2).alignment = left()

inv.merge_cells(f'B{picker_box_row}:C{picker_box_row}')
inv.cell(picker_box_row, 2).value = claims[0]['claim_no'] if claims else ''
inv.cell(picker_box_row, 2).font = font(size=14, bold=True, color=MOCOH_NAVY)
inv.cell(picker_box_row, 2).fill = fill(GOLD_PALE)
inv.cell(picker_box_row, 2).alignment = center()
for cc in range(2, 4):
    inv.cell(picker_box_row, cc).border = Border(
        left=Side(style='medium', color=MOCOH_ORANGE),
        right=Side(style='medium', color=MOCOH_ORANGE),
        top=Side(style='medium', color=MOCOH_ORANGE),
        bottom=Side(style='medium', color=MOCOH_ORANGE))
inv.row_dimensions[picker_box_row].height = 24

# IMPORTANT: the cell selected for the picker is B20, but I've been referencing $B$18 in formulas.
# Let me re-reference everything to $B$20. (Patch all VLOOKUPs above.)
# Easier: use a named range for the picker and re-write the formulas to use it. Done below.
nm['INV_CLAIM'] = DefinedName('INV_CLAIM', attr_text=f"Invoice!$B${picker_box_row}")

# Replace earlier $B$18 references with INV_CLAIM by rewriting cells
inv.cell(10, 6).value = '=IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],4,FALSE),"")'
inv.cell(11, 6).value = '=IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],5,FALSE),"")'
inv.cell(meta_val_row, 2).value = '=INV_PREFIX & TEXT(INV_NEXT + MATCH(INV_CLAIM, Claims[Claim No.], 0) - 1, "000")'
inv.cell(meta_val_row, 4).value = '=IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],2,FALSE),TODAY())'
inv.cell(meta_val_row, 6).value = '=IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],3,FALSE),"")'
inv.cell(meta_val_row, 8).value = ('=IFERROR(VLOOKUP(IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],3,FALSE),0),Deals[#All],6,FALSE),"")')

# Data validation on picker
dv_inv_claim = DataValidation(type='list', formula1='=Claims[Claim No.]', allow_blank=False)
dv_inv_claim.add(f'B{picker_box_row}')
inv.add_data_validation(dv_inv_claim)

# === Period & rate row ===
right_meta_row = picker_label_row
# F-G = PERIOD, H = LAYTIME, I-J = RATE
inv.merge_cells(f'F{right_meta_row}:G{right_meta_row}')
inv.cell(right_meta_row, 6).value = 'PERIOD'
inv.cell(right_meta_row, 6).font = font(size=9, bold=True, color=MUTED)
inv.cell(right_meta_row, 6).alignment = left()
inv.cell(right_meta_row, 8).value = 'LAYTIME'
inv.cell(right_meta_row, 8).font = font(size=9, bold=True, color=MUTED)
inv.cell(right_meta_row, 8).alignment = left()
inv.merge_cells(f'I{right_meta_row}:J{right_meta_row}')
inv.cell(right_meta_row, 9).value = 'RATE'
inv.cell(right_meta_row, 9).font = font(size=9, bold=True, color=MUTED)
inv.cell(right_meta_row, 9).alignment = left()

inv.merge_cells(f'F{picker_box_row}:G{picker_box_row}')
inv.cell(picker_box_row, 6).value = ('=TEXT(IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],6,FALSE),""),"dd-mmm")'
                                    '&" → "&TEXT(IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],7,FALSE),""),"dd-mmm")')
inv.cell(picker_box_row, 6).font = font(size=11, bold=True, color=MOCOH_NAVY)
inv.cell(picker_box_row, 6).alignment = left()

inv.cell(picker_box_row, 8).value = '=IFERROR(VLOOKUP(IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],3,FALSE),0),Deals[#All],7,FALSE),DEF_LAYTIME)&" d"'
inv.cell(picker_box_row, 8).font = font(size=11, bold=True, color=MOCOH_NAVY)
inv.cell(picker_box_row, 8).alignment = left()

inv.merge_cells(f'I{picker_box_row}:J{picker_box_row}')
inv.cell(picker_box_row, 9).value = '="$"&TEXT(IFERROR(VLOOKUP(IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],3,FALSE),0),Deals[#All],8,FALSE),DEF_RATE),"#,##0")&"/d"'
inv.cell(picker_box_row, 9).font = font(size=11, bold=True, color=MOCOH_NAVY)
inv.cell(picker_box_row, 9).alignment = left()

# === Subject ===
subj_row = picker_box_row + 2
inv.merge_cells(start_row=subj_row, start_column=2, end_row=subj_row, end_column=10)
inv.cell(subj_row, 2).value = ('="SUBJECT:  Demurrage charges — Deal "&IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],3,FALSE),"")'
                              '&" — "&IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],4,FALSE),"")')
inv.cell(subj_row, 2).font = font(size=11, bold=True, color=DARK)
inv.cell(subj_row, 2).alignment = left(indent=1)
inv.cell(subj_row, 2).fill = fill(GOLD_PALE)
for cc in range(2, 11):
    inv.cell(subj_row, cc).fill = fill(GOLD_PALE)
    inv.cell(subj_row, cc).border = Border(
        top=Side(style='thin', color=MOCOH_ORANGE), bottom=Side(style='thin', color=MOCOH_ORANGE),
        left=Side(style='thin', color=MOCOH_ORANGE) if cc==2 else None,
        right=Side(style='thin', color=MOCOH_ORANGE) if cc==10 else None)
inv.row_dimensions[subj_row].height = 24

# === LINE ITEMS: TRUCKS ON DEMURRAGE ===
# Section title
sect_row = subj_row + 2
inv.merge_cells(start_row=sect_row, start_column=2, end_row=sect_row, end_column=10)
inv.cell(sect_row, 2).value = 'TRUCKS ON DEMURRAGE'
inv.cell(sect_row, 2).font = font(size=11, bold=True, color=WHITE)
inv.cell(sect_row, 2).fill = fill(MOCOH_NAVY)
inv.cell(sect_row, 2).alignment = left(indent=1)
inv.row_dimensions[sect_row].height = 22

# Headers row
li_hdr_row = sect_row + 1
LI_HEADERS = [
    ('#',           1),
    ('Date Loaded', 1),
    ('Truck No.',   1),
    ('Arrival',     1),
    ('Offloaded',   1),
    ('Wait',        1),
    ('Lay',         1),
    ('Excess',      1),
    ('Amount (USD)',1),
]
# Place in cols B..J (9 cols)
for i, (h, _) in enumerate(LI_HEADERS):
    c = inv.cell(li_hdr_row, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(MOCOH_NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
inv.row_dimensions[li_hdr_row].height = 26

# 32 rows of line items, AGGREGATE-based (no CSE required)
N_LI = 32
for k in range(1, N_LI+1):
    r = li_hdr_row + k
    def agg(field):
        # AGGREGATE(15,6,...) = SMALL with ignore-errors; gets relative row of k-th match
        return (f'=IFERROR(INDEX(Trips[{field}],'
                f'AGGREGATE(15,6,(ROW(Trips[Claim No.])-ROW(Trips[#Headers]))/(Trips[Claim No.]=INV_CLAIM),{k})'
                f'),"")')
    # # column
    inv.cell(r, 2).value = f'=IF(J{r}="","",{k})'
    inv.cell(r, 3).value = agg('Date Loaded')
    inv.cell(r, 4).value = agg('Truck No.')
    inv.cell(r, 5).value = agg('Arrival')
    inv.cell(r, 6).value = agg('Offloaded')
    inv.cell(r, 7).value = agg('Waiting (d)')
    inv.cell(r, 8).value = agg('Laytime (d)')
    inv.cell(r, 9).value = agg('Excess (d)')
    inv.cell(r,10).value = agg('Demurrage (USD)')
    # Styles
    for col in range(2, 11):
        cc = inv.cell(r, col)
        cc.font = font(size=9)
        cc.border = Border(left=Side(style='thin', color=GRAY_RULE),
                           right=Side(style='thin', color=GRAY_RULE),
                           top=Side(style='thin', color=GRAY_RULE),
                           bottom=Side(style='thin', color=GRAY_RULE))
        cc.alignment = center()
        if k % 2 == 0: cc.fill = fill(CREAM)
    inv.cell(r, 3).number_format = FMT_DATE
    inv.cell(r, 5).number_format = FMT_DATE
    inv.cell(r, 6).number_format = FMT_DATE
    for col in (7, 8, 9):
        inv.cell(r, col).number_format = FMT_INT
    inv.cell(r,10).number_format = FMT_USD
    inv.cell(r,10).alignment = right()
    inv.row_dimensions[r].height = 14

# === Totals box ===
tot_row = li_hdr_row + N_LI + 1
def tot_line(row, label, formula, big=False, fmt=FMT_USD):
    inv.merge_cells(start_row=row, start_column=7, end_row=row, end_column=9)
    inv.cell(row, 7).value = label
    inv.cell(row, 7).font = font(size=11 if not big else 13, bold=True,
                                 color=WHITE if big else DARK)
    inv.cell(row, 7).alignment = right(indent=1)
    if big:
        inv.cell(row, 7).fill = fill(MOCOH_NAVY)
    c = inv.cell(row, 10)
    c.value = formula
    c.font = font(size=11 if not big else 14, bold=True,
                  color=WHITE if big else MOCOH_NAVY)
    c.alignment = right()
    c.number_format = fmt
    if big:
        c.fill = fill(MOCOH_NAVY)
    else:
        c.border = Border(top=Side(style='thin', color=GRAY_RULE))

subtotal_formula = '=SUMIF(Trips[Claim No.],INV_CLAIM,Trips[Demurrage (USD)])'
tot_line(tot_row,   'Subtotal',  subtotal_formula)
tot_line(tot_row+1, '="VAT ("&TEXT(VAT_RATE,"0%")&")"',
         '=SUMIF(Trips[Claim No.],INV_CLAIM,Trips[Demurrage (USD)])*VAT_RATE')
tot_line(tot_row+3, 'TOTAL DUE (USD)',
         '=ROUND(SUMIF(Trips[Claim No.],INV_CLAIM,Trips[Demurrage (USD)])*(1+VAT_RATE),2)',
         big=True, fmt=FMT_USD_DEC)
inv.row_dimensions[tot_row+3].height = 28

# === PAYMENT TERMS + DETAILS block ===
pt_row = tot_row + 6
inv.merge_cells(start_row=pt_row, start_column=2, end_row=pt_row, end_column=10)
inv.cell(pt_row, 2).value = 'PAYMENT TERMS'
inv.cell(pt_row, 2).font = font(size=10, bold=True, color=WHITE)
inv.cell(pt_row, 2).fill = fill(MOCOH_NAVY)
inv.cell(pt_row, 2).alignment = left(indent=1)
inv.row_dimensions[pt_row].height = 20

inv.merge_cells(start_row=pt_row+1, start_column=2, end_row=pt_row+1, end_column=10)
inv.cell(pt_row+1, 2).value = ('="Open account payable "&PAY_TERMS&" days from invoice date.   Due date: "'
                              '&TEXT(IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],12,FALSE),TODAY()+PAY_TERMS),"dd-mmm-yyyy")'
                              '&".   Please quote invoice number on remittance."')
inv.cell(pt_row+1, 2).font = font(size=10, color=DARK)
inv.cell(pt_row+1, 2).alignment = left(indent=1, wrap=True)
inv.row_dimensions[pt_row+1].height = 28

# Payment details title
pd_row = pt_row + 3
inv.merge_cells(start_row=pd_row, start_column=2, end_row=pd_row, end_column=10)
inv.cell(pd_row, 2).value = 'PAYMENT DETAILS — IN USD BY TELEGRAPHIC TRANSFER TO:'
inv.cell(pd_row, 2).font = font(size=10, bold=True, color=WHITE)
inv.cell(pd_row, 2).fill = fill(MOCOH_NAVY)
inv.cell(pd_row, 2).alignment = left(indent=1)
inv.row_dimensions[pd_row].height = 20

# Bank fields — three columns of labels and three columns of values
def bank_pair(row, c_start, label, value_formula):
    inv.merge_cells(start_row=row, start_column=c_start, end_row=row, end_column=c_start+2)
    inv.cell(row, c_start).value = label
    inv.cell(row, c_start).font = font(size=9, bold=True, color=MUTED)
    inv.cell(row, c_start).alignment = left(indent=1)
    inv.merge_cells(start_row=row+1, start_column=c_start, end_row=row+1, end_column=c_start+2)
    inv.cell(row+1, c_start).value = value_formula
    inv.cell(row+1, c_start).font = font(size=10, bold=True, color=MOCOH_NAVY)
    inv.cell(row+1, c_start).alignment = left(indent=1)
    inv.cell(row+1, c_start).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))

bank_pair(pd_row+1, 2, 'BENEFICIARY',         '=BANK_HOLDER')
bank_pair(pd_row+1, 5, 'BENEFICIARY BANK',    '=BANK_NAME')
bank_pair(pd_row+1, 8, 'SWIFT',               '=BANK_SWIFT')

bank_pair(pd_row+3, 2, 'IBAN / ACCOUNT',      '=BANK_IBAN')
bank_pair(pd_row+3, 5, 'CORRESPONDENT BANK',  '=BANK_CORR')
bank_pair(pd_row+3, 8, 'CORRESPONDENT SWIFT', '=BANK_CORR_SWIFT')

# Footer note
ft_row = pd_row + 6
inv.merge_cells(start_row=ft_row, start_column=2, end_row=ft_row, end_column=10)
inv.cell(ft_row, 2).value = '=INV_FOOTER'
inv.cell(ft_row, 2).font = font(size=9, italic=True, color=MUTED)
inv.cell(ft_row, 2).alignment = left(wrap=True)
inv.row_dimensions[ft_row].height = 36

# Signature + stamp at bottom
sig_row = ft_row + 2
inv.cell(sig_row, 2).value = 'For and on behalf of'
inv.cell(sig_row, 2).font = font(size=9, color=MUTED)
inv.cell(sig_row, 2).alignment = left()
inv.cell(sig_row+1, 2).value = '=COMPANY_NAME'
inv.cell(sig_row+1, 2).font = font(size=11, bold=True, color=MOCOH_NAVY)
inv.cell(sig_row+1, 2).alignment = left()

# Place signature image
try:
    sig_img = XLImage('/home/user/test/assets/signature.jpeg')
    sig_img.height = 35
    sig_img.width = 100
    inv.add_image(sig_img, f'B{sig_row+2}')
except FileNotFoundError:
    pass

# Place stamp image to the right
try:
    stamp_img = XLImage('/home/user/test/assets/stamp.jpeg')
    stamp_img.height = 80
    stamp_img.width = 80
    inv.add_image(stamp_img, f'I{sig_row}')
except FileNotFoundError:
    pass

# Print area
inv.print_area = f'A1:K{sig_row+5}'

# ============================================================
# 8. DASHBOARD
# ============================================================
dash = wb.create_sheet('Dashboard')
dash.sheet_view.showGridLines = False
dash.sheet_view.showRowColHeaders = False
widths_d = {'A':2, 'B':22,'C':22,'D':22,'E':22,'F':22,'G':22,'H':22,'I':22, 'J':2}
for col, w in widths_d.items():
    dash.column_dimensions[col].width = w

dash.merge_cells('B2:I2')
dash.cell(2,2).value = 'DEMURRAGE DASHBOARD'
dash.cell(2,2).font = font(size=24, bold=True, color=MOCOH_NAVY)
dash.cell(2,2).alignment = left()
dash.row_dimensions[2].height = 36
dash.merge_cells('B3:I3')
dash.cell(3,2).value = 'Live KPIs across trips, claims and invoices.'
dash.cell(3,2).font = font(size=10, italic=True, color=MUTED)
for c in range(2, 10):
    dash.cell(4, c).border = Border(top=Side(style='medium', color=MOCOH_ORANGE))
dash.row_dimensions[4].height = 6

def dash_kpi(row, col, label, formula, fmt=FMT_USD):
    dash.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col+1)
    dash.cell(row, col).value = label
    dash.cell(row, col).font = font(size=10, bold=True, color=WHITE)
    dash.cell(row, col).fill = fill(MOCOH_NAVY)
    dash.cell(row, col).alignment = center()
    dash.row_dimensions[row].height = 22
    dash.merge_cells(start_row=row+1, start_column=col, end_row=row+2, end_column=col+1)
    c = dash.cell(row+1, col)
    c.value = formula
    c.font = font(size=20, bold=True, color=MOCOH_NAVY)
    c.fill = fill(WHITE)
    c.alignment = center()
    c.number_format = fmt
    for rr in range(row, row+3):
        for cc in range(col, col+2):
            dash.cell(rr, cc).border = Border(
                left=Side(style='thin', color=MOCOH_ORANGE),
                right=Side(style='thin', color=MOCOH_ORANGE),
                top=Side(style='thin', color=MOCOH_ORANGE),
                bottom=Side(style='thin', color=MOCOH_ORANGE))

dash_kpi(6, 2, 'TOTAL DEMURRAGE',  '=SUM(Trips[Demurrage (USD)])', FMT_USD)
dash_kpi(6, 4, 'TRIPS',            '=ROWS(Trips[Deal No.])',       FMT_INT)
dash_kpi(6, 6, 'IN DEMURRAGE',     '=COUNTIF(Trips[Status],"DEMURRAGE")', FMT_INT)
dash_kpi(6, 8, 'AVG / TRIP',       '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)', FMT_USD)

dash_kpi(10, 2, 'INVOICED', '=SUMIFS(Claims[Amount (USD)],Claims[Status],"Sent")+SUMIFS(Claims[Amount (USD)],Claims[Status],"Paid")', FMT_USD)
dash_kpi(10, 4, 'PAID',     '=SUMIF(Claims[Status],"Paid",Claims[Amount (USD)])', FMT_USD)
dash_kpi(10, 6, 'OUTSTANDING','=SUMIF(Claims[Status],"Sent",Claims[Amount (USD)])', FMT_USD)
dash_kpi(10, 8, 'OVERDUE',  '=SUMIFS(Claims[Amount (USD)],Claims[Status],"Sent",Claims[Days Overdue],">0")', FMT_USD)

def breakdown(start_row, col_start, title, headers, rows_data):
    span = len(headers)
    end_col = col_start + span - 1
    dash.merge_cells(start_row=start_row, start_column=col_start, end_row=start_row, end_column=end_col)
    c = dash.cell(start_row, col_start)
    c.value = title; c.font = font(size=12, bold=True, color=WHITE); c.fill = fill(MOCOH_NAVY)
    c.alignment = left(indent=1)
    dash.row_dimensions[start_row].height = 24
    hr = start_row + 1
    for i, h in enumerate(headers):
        cc = dash.cell(hr, col_start+i)
        cc.value = h
        cc.font = font(size=10, bold=True, color=MOCOH_NAVY)
        cc.fill = fill(GOLD_PALE)
        cc.alignment = center() if i>0 else left(indent=1)
        cc.border = Border(left=thin, right=thin, top=thin,
                          bottom=Side(style='medium', color=MOCOH_ORANGE))
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
        cc.font = font(size=10, bold=True, color=WHITE)
        cc.fill = fill(MOCOH_NAVY)
        cc.alignment = left(indent=1) if j==0 else right()
        cc.border = Border(top=Side(style='medium', color=MOCOH_ORANGE))
    dash.cell(tr, col_start).value = 'TOTAL'
    return tr

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

aging_rows = [
    ['Current (not yet due)', '=COUNTIF(Claims[Aging],"Current")', '=SUMIF(Claims[Aging],"Current",Claims[Amount (USD)])'],
    ['1–30 days overdue',     '=COUNTIF(Claims[Aging],"1-30")',    '=SUMIF(Claims[Aging],"1-30",Claims[Amount (USD)])'],
    ['31–60 days overdue',    '=COUNTIF(Claims[Aging],"31-60")',   '=SUMIF(Claims[Aging],"31-60",Claims[Amount (USD)])'],
    ['60+ days overdue',      '=COUNTIF(Claims[Aging],"60+")',     '=SUMIF(Claims[Aging],"60+",Claims[Amount (USD)])'],
    ['Paid',                  '=COUNTIF(Claims[Aging],"Paid")',    '=SUMIF(Claims[Aging],"Paid",Claims[Amount (USD)])'],
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
    'Cover': MOCOH_NAVY,
    'Dashboard': MOCOH_ORANGE,
    'Invoice': MOCOH_ORANGE,
    'Claims': MOCOH_ORANGE,
    'Trips Ledger': MOCOH_NAVY,
    'Deals': MOCOH_NAVY,
    'Assumptions': MUTED,
    'Company': MUTED,
}
for s, c in color_map.items():
    wb[s].sheet_properties.tabColor = c

wb.active = 0

out = '/home/user/test/MOCOH_DEMURRAGE_2026.xlsx'
wb.save(out)
print('Saved:', out)
import os
print('Size:', os.path.getsize(out), 'bytes')
print('Sheets:', wb.sheetnames)
print('Trips:', len(trips), 'Claims:', len(claims))
print('Total demurrage:', f"${sum((t['demurrage'] or 0) for t in trips):,}")
