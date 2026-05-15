"""Build a Vitol-style demurrage workbook from extracted data."""
import pickle
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, NamedStyle
)
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import (
    CellIsRule, FormulaRule, ColorScaleRule, IconSetRule
)
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

with open('/tmp/data.pkl','rb') as f:
    data = pickle.load(f)
deals = data['deals']
trips = data['trips']

# Normalize transporter names
def norm_transporter(t):
    if t is None: return None
    return t.strip().upper().replace('TRUCKEAZE','TRUCKEAZE')
for t in trips:
    t['transporter'] = norm_transporter(t['transporter'])
    t['consignee'] = (t['consignee'] or '').strip()

# === Style palette (Vitol-style) ===
NAVY = '0B2447'
NAVY_MID = '19376D'
NAVY_LIGHT = '576CBC'
GOLD = 'C9A227'
GOLD_LIGHT = 'F4E1A4'
GOLD_PALE = 'FDF4D4'
CREAM = 'FDFBF7'
GRAY_RULE = 'E5E7EB'
GRAY_HEADER = 'F3F4F6'
RED_BG = 'FCE4E4'
RED_FG = '991B1B'
GREEN_BG = 'DCFCE7'
GREEN_FG = '166534'
WHITE = 'FFFFFF'
DARK = '111827'
MUTED = '6B7280'

thin = Side(style='thin', color=GRAY_RULE)
thin_dark = Side(style='thin', color=DARK)
medium_gold = Side(style='medium', color=GOLD)
border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
border_bottom_gold = Border(bottom=medium_gold)

def font(size=11, bold=False, color=DARK, italic=False):
    return Font(name='Calibri', size=size, bold=bold, color=color, italic=italic)

def fill(color):
    return PatternFill('solid', fgColor=color)

def center(wrap=False):
    return Alignment(horizontal='center', vertical='center', wrap_text=wrap)

def left(wrap=False, indent=0):
    return Alignment(horizontal='left', vertical='center', wrap_text=wrap, indent=indent)

def right(wrap=False):
    return Alignment(horizontal='right', vertical='center', wrap_text=wrap)

wb = Workbook()
wb.remove(wb.active)

# Reusable formats
FMT_USD = '_-[$$-409]* #,##0_-;[Red]-[$$-409]* #,##0_-;_-[$$-409]* "-"??_-;_-@_-'
FMT_USD_DEC = '_-[$$-409]* #,##0.00_-;[Red]-[$$-409]* #,##0.00_-'
FMT_INT = '#,##0;[Red]-#,##0;"-"'
FMT_DATE = 'dd-mmm-yyyy'
FMT_PCT = '0.0%'

# ============================================================
# 1. COVER SHEET
# ============================================================
cover = wb.create_sheet('Cover')
cover.sheet_view.showGridLines = False
cover.sheet_view.showRowColHeaders = False

# Set column widths and row heights for the cover
for col, w in zip('ABCDEFGHIJ', [3,18,18,18,18,18,18,18,18,3]):
    cover.column_dimensions[col].width = w
for r in range(1, 40):
    cover.row_dimensions[r].height = 18

# Big navy header band rows 2-6
for r in range(2, 7):
    for c in range(1, 11):
        cover.cell(r, c).fill = fill(NAVY)

cover.merge_cells('B3:I4')
cover.cell(3,2).value = 'DEMURRAGE STATEMENT'
cover.cell(3,2).font = font(size=32, bold=True, color=WHITE)
cover.cell(3,2).alignment = Alignment(horizontal='left', vertical='center')

cover.merge_cells('B5:I5')
cover.cell(5,2).value = 'TRUCKING  •  BEIRA → LUSAKA CORRIDOR  •  2026'
cover.cell(5,2).font = font(size=12, bold=True, color=GOLD_LIGHT)
cover.cell(5,2).alignment = Alignment(horizontal='left', vertical='center')

# Gold rule row 7
for c in range(1, 11):
    cover.cell(7, c).fill = fill(GOLD)
cover.row_dimensions[7].height = 4

# Document info block
def cover_label(row, label, value, value_fmt=None):
    cover.cell(row, 2).value = label
    cover.cell(row, 2).font = font(size=10, color=MUTED, bold=True)
    cover.cell(row, 2).alignment = left()
    cover.merge_cells(start_row=row, start_column=4, end_row=row, end_column=9)
    c = cover.cell(row, 4)
    c.value = value
    c.font = font(size=12, color=DARK, bold=True)
    c.alignment = left()
    if value_fmt: c.number_format = value_fmt
    cover.cell(row, 2).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))
    for cc in range(4, 10):
        cover.cell(row, cc).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))

cover_label(10, 'Document', 'Demurrage Calculation — Trucking')
cover_label(12, 'Period',   'January – April 2026')
cover_label(14, 'Currency', 'USD')
cover_label(16, 'Prepared by', '—')
cover_label(18, 'Reviewed by', '—')
cover_label(20, 'Issue date', datetime(2026,5,15), FMT_DATE)

# KPI cards
cover.cell(24, 2).value = 'PORTFOLIO AT A GLANCE'
cover.cell(24, 2).font = font(size=12, bold=True, color=NAVY)

def kpi(row, col_start, label, value_cell):
    cover.merge_cells(start_row=row, start_column=col_start, end_row=row, end_column=col_start+1)
    cover.merge_cells(start_row=row+1, start_column=col_start, end_row=row+2, end_column=col_start+1)
    cover.cell(row, col_start).value = label
    cover.cell(row, col_start).font = font(size=9, bold=True, color=WHITE)
    cover.cell(row, col_start).alignment = center()
    cover.cell(row, col_start).fill = fill(NAVY_MID)
    cover.cell(row+1, col_start).value = value_cell
    cover.cell(row+1, col_start).font = font(size=18, bold=True, color=NAVY)
    cover.cell(row+1, col_start).alignment = center()
    cover.cell(row+1, col_start).fill = fill(CREAM)
    for rr in range(row, row+3):
        for cc in range(col_start, col_start+2):
            cell = cover.cell(rr, cc)
            cell.border = Border(left=Side(style='thin', color=GOLD),
                                 right=Side(style='thin', color=GOLD),
                                 top=Side(style='thin', color=GOLD),
                                 bottom=Side(style='thin', color=GOLD))

kpi(26, 2, 'TOTAL DEMURRAGE (USD)', '=Dashboard!E6')
kpi(26, 4, 'TRIPS IN DEMURRAGE',    '=Dashboard!E10')
kpi(26, 6, 'TOTAL TRIPS',           '=Dashboard!E8')
kpi(26, 8, 'AVG / TRIP (USD)',      '=Dashboard!E12')

# Format the USD KPIs
cover.cell(27, 2).number_format = FMT_USD
cover.cell(27, 4).number_format = '#,##0" / "0'
cover.cell(27, 6).number_format = FMT_INT
cover.cell(27, 8).number_format = FMT_USD

# Footer
cover.merge_cells('B36:I36')
cover.cell(36, 2).value = 'CONFIDENTIAL  •  Internal use only  •  Generated from Trips Ledger'
cover.cell(36, 2).font = font(size=9, italic=True, color=MUTED)
cover.cell(36, 2).alignment = center()

# ============================================================
# 2. ASSUMPTIONS
# ============================================================
asm = wb.create_sheet('Assumptions')
asm.sheet_view.showGridLines = False

asm.column_dimensions['A'].width = 2
asm.column_dimensions['B'].width = 34
asm.column_dimensions['C'].width = 22
asm.column_dimensions['D'].width = 50

# Title band
asm.merge_cells('B2:D2')
asm.cell(2,2).value = 'ASSUMPTIONS & DEFAULTS'
asm.cell(2,2).font = font(size=20, bold=True, color=NAVY)
asm.cell(2,2).alignment = left()
asm.row_dimensions[2].height = 32

asm.merge_cells('B3:D3')
asm.cell(3,2).value = 'Edit yellow cells to update the entire workbook.'
asm.cell(3,2).font = font(size=10, italic=True, color=MUTED)

# Gold rule
for c in range(2, 5):
    asm.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))
asm.row_dimensions[4].height = 6

def asm_section(row, title):
    asm.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    asm.cell(row,2).value = title
    asm.cell(row,2).font = font(size=11, bold=True, color=WHITE)
    asm.cell(row,2).fill = fill(NAVY_MID)
    asm.cell(row,2).alignment = left(indent=1)
    asm.row_dimensions[row].height = 22

def asm_row(row, label, value, note='', fmt=None, input_cell=True):
    asm.cell(row, 2).value = label
    asm.cell(row, 2).font = font(size=11, color=DARK)
    asm.cell(row, 2).alignment = left(indent=1)
    asm.cell(row, 2).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))

    c = asm.cell(row, 3)
    c.value = value
    c.font = font(size=11, bold=True, color=NAVY)
    c.alignment = center()
    c.fill = fill(GOLD_PALE if input_cell else WHITE)
    c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    if fmt: c.number_format = fmt

    asm.cell(row, 4).value = note
    asm.cell(row, 4).font = font(size=10, italic=True, color=MUTED)
    asm.cell(row, 4).alignment = left(indent=1)
    asm.row_dimensions[row].height = 20

asm_section(6, 'COMMERCIAL DEFAULTS')
asm_row(7, 'Default laytime (days)',      2,    'Free time at offloading site before demurrage accrues.')
asm_row(8, 'Default demurrage rate (USD/day)', 250, 'Per-truck per-day charge once laytime is exceeded.')
asm_row(9, 'Currency',                    'USD', 'Reporting currency for all amounts.', input_cell=True)
asm_row(10, 'FX rate (local → USD)',      1.00, 'Set to 1.00 if invoices are already in USD.', fmt='0.0000')

asm_section(12, 'REPORTING PERIOD')
asm_row(13, 'Period start',  datetime(2026,1,1), 'Inclusive.', fmt=FMT_DATE)
asm_row(14, 'Period end',    datetime(2026,4,30), 'Inclusive.', fmt=FMT_DATE)
asm_row(15, 'Report issued', datetime(2026,5,15), '', fmt=FMT_DATE)

asm_section(17, 'TOLERANCES & FLAGS')
asm_row(18, 'Min. waiting days to flag review', 7, 'Trips above this are highlighted as outliers.')
asm_row(19, 'Sanity tolerance (days)', 0, 'Days of grace before flagging a date inconsistency.')

# Named ranges
wb.defined_names['DEF_LAYTIME'] = DefinedName('DEF_LAYTIME', attr_text="Assumptions!$C$7")
wb.defined_names['DEF_RATE']    = DefinedName('DEF_RATE',    attr_text="Assumptions!$C$8")
wb.defined_names['CCY']         = DefinedName('CCY',         attr_text="Assumptions!$C$9")
wb.defined_names['FX']          = DefinedName('FX',          attr_text="Assumptions!$C$10")
wb.defined_names['PERIOD_START']= DefinedName('PERIOD_START',attr_text="Assumptions!$C$13")
wb.defined_names['PERIOD_END']  = DefinedName('PERIOD_END',  attr_text="Assumptions!$C$14")
wb.defined_names['OUTLIER_DAYS']= DefinedName('OUTLIER_DAYS',attr_text="Assumptions!$C$18")

# ============================================================
# 3. DEALS MASTER
# ============================================================
dm = wb.create_sheet('Deals')
dm.sheet_view.showGridLines = False

for col, w in zip('ABCDEFGHIJK', [2,12,30,20,16,16,12,12,18,18,16]):
    dm.column_dimensions[col].width = w

dm.merge_cells('B2:K2')
dm.cell(2,2).value = 'DEALS MASTER'
dm.cell(2,2).font = font(size=20, bold=True, color=NAVY)
dm.cell(2,2).alignment = left()
dm.row_dimensions[2].height = 32

dm.merge_cells('B3:K3')
dm.cell(3,2).value = 'Central register of all demurrage deals. Edit here; the Trips Ledger and Dashboard refresh automatically.'
dm.cell(3,2).font = font(size=10, italic=True, color=MUTED)

for c in range(2, 12):
    dm.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))

headers = ['Deal No.','Consignee','Route','Loading Port','Destination','Product',
           'Laytime (days)','Rate (USD/day)','Transport (USD/m³)','Transporter']
header_row = 6
for i, h in enumerate(headers):
    c = dm.cell(header_row, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
dm.row_dimensions[header_row].height = 36

# Write data
for i, d in enumerate(deals):
    r = header_row + 1 + i
    row_vals = [d['deal'], d['consignee'], d['route'], d['loading_port'], d['destination'],
                d['product'], d['laytime'], d['rate'], d['transport_rate'], d['transporter']]
    for j, v in enumerate(row_vals):
        c = dm.cell(r, 2+j)
        c.value = v
        c.font = font(size=10)
        c.alignment = left(indent=1) if j in (1,2,3,4,5,9) else center()
        c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        if i % 2 == 0:
            c.fill = fill(CREAM)
    dm.cell(r, 2+6).number_format = FMT_INT
    dm.cell(r, 2+7).number_format = FMT_USD
    dm.cell(r, 2+8).number_format = '#,##0.00;"-"'

# Make it an Excel table
last_row = header_row + len(deals)
tbl = Table(displayName='Deals',
            ref=f'B{header_row}:K{last_row}')
tbl.tableStyleInfo = TableStyleInfo(name='TableStyleLight1',
    showRowStripes=False, showColumnStripes=False)
dm.add_table(tbl)

dm.freeze_panes = 'B7'

# ============================================================
# 4. TRIPS LEDGER  (consolidated)
# ============================================================
tl = wb.create_sheet('Trips Ledger')
tl.sheet_view.showGridLines = False

trip_cols = [
    ('Deal No.',     10),
    ('Consignee',    24),
    ('Date Loaded',  13),
    ('Loading Port', 12),
    ('Destination',  12),
    ('Product',       9),
    ('Truck No.',    13),
    ('Trailer Reg.', 13),
    ('Transporter',  14),
    ('Driver',       22),
    ('Arrival',      13),
    ('Offloaded',    13),
    ('Waiting (d)',  10),
    ('Laytime (d)',  10),
    ('Excess (d)',   10),
    ('Rate (USD)',   11),
    ('Demurrage (USD)', 14),
    ('Status',       13),
    ('Sanity',       16),
    ('Month',        10),
]

tl.column_dimensions['A'].width = 2
for i, (h, w) in enumerate(trip_cols):
    tl.column_dimensions[get_column_letter(2+i)].width = w

last_col_letter = get_column_letter(2+len(trip_cols)-1)
tl.merge_cells(f'B2:{last_col_letter}2')
tl.cell(2,2).value = 'TRIPS LEDGER'
tl.cell(2,2).font = font(size=20, bold=True, color=NAVY)
tl.cell(2,2).alignment = left()
tl.row_dimensions[2].height = 32

tl.merge_cells(f'B3:{last_col_letter}3')
tl.cell(3,2).value = ('Single source of truth for every truck movement. '
                     'Add new rows at the bottom — formulas extend automatically inside the table.')
tl.cell(3,2).font = font(size=10, italic=True, color=MUTED)

for c in range(2, 2+len(trip_cols)):
    tl.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))

header_row = 6
for i, (h, _) in enumerate(trip_cols):
    c = tl.cell(header_row, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
tl.row_dimensions[header_row].height = 36

# Write trip data
for i, t in enumerate(trips):
    r = header_row + 1 + i
    deal = t['deal']
    # Column letters: B..U
    tl.cell(r, 2).value = deal
    tl.cell(r, 3).value = t['consignee']
    tl.cell(r, 4).value = t['date_loaded']
    tl.cell(r, 5).value = t['loading_port']
    tl.cell(r, 6).value = t['destination']
    tl.cell(r, 7).value = t['product']
    tl.cell(r, 8).value = t['truck']
    tl.cell(r, 9).value = t['trailer']
    tl.cell(r,10).value = t['transporter']
    tl.cell(r,11).value = t['driver']
    tl.cell(r,12).value = t['arrival']
    tl.cell(r,13).value = t['offloaded']
    # Waiting: formula L - K
    tl.cell(r,14).value = f'=IF(OR(K{r}="",L{r}="" ),"",L{r}-K{r})'
    # Laytime: lookup from Deals
    tl.cell(r,15).value = f'=IFERROR(VLOOKUP(B{r},Deals[#All],7,FALSE),DEF_LAYTIME)'
    # Excess
    tl.cell(r,16).value = f'=IF(N{r}="","",MAX(0,N{r}-O{r}))'
    # Rate
    tl.cell(r,17).value = f'=IFERROR(VLOOKUP(B{r},Deals[#All],8,FALSE),DEF_RATE)'
    # Demurrage = Excess * Rate
    tl.cell(r,18).value = f'=IF(P{r}="","",P{r}*Q{r})'
    # Status
    tl.cell(r,19).value = f'=IF(N{r}="","PENDING",IF(P{r}>0,"DEMURRAGE","ON-TIME"))'
    # Sanity
    tl.cell(r,20).value = (f'=IF(AND(D{r}<>"",K{r}<>"",K{r}<D{r}),"⚠ Arr<Loaded",'
                          f'IF(AND(K{r}<>"",L{r}<>"",L{r}<K{r}),"⚠ Off<Arr","OK"))')
    # Month
    tl.cell(r,21).value = f'=IF(D{r}="","",TEXT(D{r},"yyyy-mm"))'

last_row = header_row + len(trips)

# Formats and styles for data rows
for r in range(header_row+1, last_row+1):
    for j in range(len(trip_cols)):
        c = tl.cell(r, 2+j)
        c.font = font(size=10)
        c.border = Border(left=Side(style='thin', color=GRAY_RULE),
                          right=Side(style='thin', color=GRAY_RULE),
                          top=Side(style='thin', color=GRAY_RULE),
                          bottom=Side(style='thin', color=GRAY_RULE))
        c.alignment = left(indent=1)
    # Numeric / date alignments
    tl.cell(r, 2).alignment = center()        # Deal
    tl.cell(r, 4).number_format = FMT_DATE
    tl.cell(r, 4).alignment = center()
    tl.cell(r,12).number_format = FMT_DATE
    tl.cell(r,12).alignment = center()
    tl.cell(r,13).number_format = FMT_DATE
    tl.cell(r,13).alignment = center()
    tl.cell(r,14).number_format = FMT_INT
    tl.cell(r,14).alignment = center()
    tl.cell(r,15).number_format = FMT_INT
    tl.cell(r,15).alignment = center()
    tl.cell(r,16).number_format = FMT_INT
    tl.cell(r,16).alignment = center()
    tl.cell(r,17).number_format = FMT_USD
    tl.cell(r,17).alignment = right()
    tl.cell(r,18).number_format = FMT_USD
    tl.cell(r,18).alignment = right()
    tl.cell(r,19).alignment = center()
    tl.cell(r,20).alignment = center()
    tl.cell(r,21).alignment = center()

# Excel Table on it
trip_ref = f'B{header_row}:{last_col_letter}{last_row}'
tt = Table(displayName='Trips', ref=trip_ref)
tt.tableStyleInfo = TableStyleInfo(name='TableStyleLight1',
    showRowStripes=True, showColumnStripes=False)
tl.add_table(tt)

# Conditional formatting on Status column (column S = col 19)
status_range = f'S{header_row+1}:S{last_row}'
tl.conditional_formatting.add(status_range,
    CellIsRule(operator='equal', formula=['"DEMURRAGE"'],
               fill=fill(RED_BG), font=font(bold=True, color=RED_FG)))
tl.conditional_formatting.add(status_range,
    CellIsRule(operator='equal', formula=['"ON-TIME"'],
               fill=fill(GREEN_BG), font=font(bold=True, color=GREEN_FG)))
tl.conditional_formatting.add(status_range,
    CellIsRule(operator='equal', formula=['"PENDING"'],
               fill=fill(GOLD_PALE), font=font(bold=True, color=NAVY)))

# Heat-map on Waiting column (N)
wait_range = f'N{header_row+1}:N{last_row}'
tl.conditional_formatting.add(wait_range,
    ColorScaleRule(start_type='num', start_value=0, start_color='DCFCE7',
                   mid_type='num', mid_value=7, mid_color='FEF3C7',
                   end_type='num', end_value=15, end_color='FCA5A5'))

# Sanity column highlight
san_range = f'T{header_row+1}:T{last_row}'
tl.conditional_formatting.add(san_range,
    FormulaRule(formula=[f'LEFT(T{header_row+1},1)="⚠"'],
                fill=fill(RED_BG), font=font(bold=True, color=RED_FG)))

# Totals row at the bottom (outside the table for clarity)
tot_row = last_row + 2
tl.cell(tot_row, 2).value = 'TOTAL'
tl.cell(tot_row, 2).font = font(bold=True, color=WHITE)
tl.cell(tot_row, 2).fill = fill(NAVY)
tl.cell(tot_row, 2).alignment = center()
for j in range(2, 2+len(trip_cols)):
    tl.cell(tot_row, j).fill = fill(NAVY)
    tl.cell(tot_row, j).font = font(bold=True, color=WHITE)
tl.cell(tot_row, 14).value = f'=SUBTOTAL(109,Trips[Waiting (d)])'
tl.cell(tot_row, 14).number_format = FMT_INT
tl.cell(tot_row, 14).alignment = center()
tl.cell(tot_row, 16).value = f'=SUBTOTAL(109,Trips[Excess (d)])'
tl.cell(tot_row, 16).number_format = FMT_INT
tl.cell(tot_row, 16).alignment = center()
tl.cell(tot_row, 18).value = f'=SUBTOTAL(109,Trips[Demurrage (USD)])'
tl.cell(tot_row, 18).number_format = FMT_USD
tl.cell(tot_row, 18).alignment = right()

tl.freeze_panes = f'D{header_row+1}'

# Print setup
tl.page_setup.orientation = tl.ORIENTATION_LANDSCAPE
tl.page_setup.fitToWidth = 1
tl.sheet_properties.pageSetUpPr.fitToPage = True
tl.print_options.horizontalCentered = True
tl.print_title_rows = f'{header_row}:{header_row}'

# ============================================================
# 5. DASHBOARD
# ============================================================
dash = wb.create_sheet('Dashboard')
dash.sheet_view.showGridLines = False
dash.sheet_view.showRowColHeaders = False

# Column widths
widths = {'A':2, 'B':22,'C':22,'D':22,'E':22,'F':22,'G':22,'H':22,'I':22, 'J':2}
for col, w in widths.items():
    dash.column_dimensions[col].width = w

# Title
dash.merge_cells('B2:I2')
dash.cell(2,2).value = 'DEMURRAGE DASHBOARD'
dash.cell(2,2).font = font(size=24, bold=True, color=NAVY)
dash.cell(2,2).alignment = left()
dash.row_dimensions[2].height = 36

dash.merge_cells('B3:I3')
dash.cell(3,2).value = 'Live KPIs and breakdowns. All figures recompute from the Trips Ledger.'
dash.cell(3,2).font = font(size=10, italic=True, color=MUTED)

for c in range(2, 10):
    dash.cell(4, c).border = Border(top=Side(style='medium', color=GOLD))
dash.row_dimensions[4].height = 6

# KPI card helper (2-col wide cards)
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
    c.font = font(size=22, bold=True, color=NAVY)
    c.fill = fill(WHITE)
    c.alignment = center()
    c.number_format = fmt
    dash.row_dimensions[row+1].height = 22
    dash.row_dimensions[row+2].height = 22

    for rr in range(row, row+3):
        for cc in range(col, col+2):
            cell = dash.cell(rr, cc)
            existing = cell.border
            cell.border = Border(
                left=Side(style='thin', color=GOLD),
                right=Side(style='thin', color=GOLD),
                top=Side(style='thin', color=GOLD),
                bottom=Side(style='thin', color=GOLD),
            )

# Row 6-8: KPI cards
dash_kpi(6, 2, 'TOTAL DEMURRAGE',     '=SUM(Trips[Demurrage (USD)])', FMT_USD)
dash_kpi(6, 4, 'TOTAL TRIPS',         '=ROWS(Trips[Deal No.])',       FMT_INT)
dash_kpi(6, 6, 'IN DEMURRAGE',        '=COUNTIF(Trips[Status],"DEMURRAGE")', FMT_INT)
dash_kpi(6, 8, 'AVG / TRIP',          '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)', FMT_USD)

# Second row of KPIs
dash_kpi(10, 2, 'AVG EXCESS DAYS',    '=IFERROR(SUMPRODUCT(Trips[Excess (d)])/COUNT(Trips[Excess (d)]),0)', '0.0')
dash_kpi(10, 4, 'MAX EXCESS DAYS',    '=IFERROR(MAX(Trips[Excess (d)]),0)', FMT_INT)
dash_kpi(10, 6, 'ACTIVE DEALS',       '=SUMPRODUCT((COUNTIF(Trips[Deal No.],Deals[Deal No.])>0)*1)', FMT_INT)
dash_kpi(10, 8, '% TRIPS IN DEMURRAGE','=IFERROR(COUNTIF(Trips[Status],"DEMURRAGE")/ROWS(Trips[Deal No.]),0)', FMT_PCT)

# === Breakdown tables ===
def breakdown_table(start_row, col_start, title, headers, rows_data, total_formulas=None):
    """rows_data: list of [label, formula1, formula2, ...]"""
    span = len(headers)
    end_col = col_start + span - 1
    # title bar
    dash.merge_cells(start_row=start_row, start_column=col_start, end_row=start_row, end_column=end_col)
    c = dash.cell(start_row, col_start)
    c.value = title
    c.font = font(size=12, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = left(indent=1)
    dash.row_dimensions[start_row].height = 24

    # headers
    hr = start_row + 1
    for i, h in enumerate(headers):
        cc = dash.cell(hr, col_start+i)
        cc.value = h
        cc.font = font(size=10, bold=True, color=NAVY)
        cc.fill = fill(GOLD_PALE)
        cc.alignment = center() if i>0 else left(indent=1)
        cc.border = Border(left=thin, right=thin, top=thin, bottom=Side(style='medium', color=GOLD))
    dash.row_dimensions[hr].height = 22

    # rows
    for i, rd in enumerate(rows_data):
        r = hr + 1 + i
        for j, v in enumerate(rd):
            cc = dash.cell(r, col_start+j)
            cc.value = v
            cc.font = font(size=10)
            cc.alignment = left(indent=1) if j==0 else right()
            cc.border = Border(left=thin, right=thin, top=Side(style='dotted', color=GRAY_RULE), bottom=Side(style='dotted', color=GRAY_RULE))
            if i % 2 == 1:
                cc.fill = fill(CREAM)
        # Default number formats per column
        dash.cell(r, col_start+1).number_format = FMT_INT
        if span >= 3: dash.cell(r, col_start+2).number_format = FMT_USD
        if span >= 4: dash.cell(r, col_start+3).number_format = FMT_USD

    # total
    tr = hr + 1 + len(rows_data)
    dash.cell(tr, col_start).value = 'TOTAL'
    for j in range(span):
        cc = dash.cell(tr, col_start+j)
        cc.font = font(size=10, bold=True, color=WHITE)
        cc.fill = fill(NAVY)
        cc.alignment = left(indent=1) if j==0 else right()
        cc.border = Border(top=Side(style='medium', color=GOLD))
    if total_formulas:
        for j, fml in enumerate(total_formulas, start=1):
            cc = dash.cell(tr, col_start+j)
            cc.value = fml
            if j == 1: cc.number_format = FMT_INT
            else: cc.number_format = FMT_USD
    return tr

# --- BY CONSIGNEE ---
consignees = sorted(set(d['consignee'] for d in deals if d['consignee']))
rows_by_consignee = []
for cn in consignees:
    rows_by_consignee.append([
        cn,
        f'=COUNTIFS(Trips[Consignee],B{0})'.replace('{0}', '$$') ,  # placeholder
    ])
# Rebuild properly with actual cells
rows_by_consignee = []
for cn in consignees:
    rows_by_consignee.append([
        cn,
        f'=COUNTIF(Trips[Consignee],"{cn}")',
        f'=SUMIF(Trips[Consignee],"{cn}",Trips[Demurrage (USD)])',
        f'=IFERROR(SUMIF(Trips[Consignee],"{cn}",Trips[Demurrage (USD)])/COUNTIF(Trips[Consignee],"{cn}"),0)',
    ])

end_consignee = breakdown_table(
    14, 2,
    'BY CONSIGNEE',
    ['Consignee', 'Trips', 'Total Demurrage', 'Avg / Trip'],
    rows_by_consignee,
    total_formulas=[
        '=SUM(Trips[Deal No.])/AVERAGE(Trips[Deal No.])' ,  # silly, replace
    ],
)
# Replace the total formulas with proper ones (cleaner)
dash.cell(end_consignee, 3).value = '=ROWS(Trips[Deal No.])'
dash.cell(end_consignee, 3).number_format = FMT_INT
dash.cell(end_consignee, 4).value = '=SUM(Trips[Demurrage (USD)])'
dash.cell(end_consignee, 4).number_format = FMT_USD
dash.cell(end_consignee, 5).value = '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)'
dash.cell(end_consignee, 5).number_format = FMT_USD

# --- BY TRANSPORTER ---
transporters = sorted(set(t['transporter'] for t in trips if t['transporter']))
rows_by_transporter = []
for tr in transporters:
    rows_by_transporter.append([
        tr,
        f'=COUNTIF(Trips[Transporter],"{tr}")',
        f'=SUMIF(Trips[Transporter],"{tr}",Trips[Demurrage (USD)])',
        f'=IFERROR(SUMIF(Trips[Transporter],"{tr}",Trips[Demurrage (USD)])/COUNTIF(Trips[Transporter],"{tr}"),0)',
    ])

start_tr = end_consignee + 3
end_tr = breakdown_table(
    start_tr, 2,
    'BY TRANSPORTER',
    ['Transporter', 'Trips', 'Total Demurrage', 'Avg / Trip'],
    rows_by_transporter,
)
dash.cell(end_tr, 3).value = '=ROWS(Trips[Deal No.])'
dash.cell(end_tr, 3).number_format = FMT_INT
dash.cell(end_tr, 4).value = '=SUM(Trips[Demurrage (USD)])'
dash.cell(end_tr, 4).number_format = FMT_USD
dash.cell(end_tr, 5).value = '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)'
dash.cell(end_tr, 5).number_format = FMT_USD

# --- BY MONTH ---
months = sorted({t['date_loaded'].strftime('%Y-%m') for t in trips if t['date_loaded']})
rows_by_month = []
for m in months:
    rows_by_month.append([
        m,
        f'=COUNTIF(Trips[Month],"{m}")',
        f'=SUMIF(Trips[Month],"{m}",Trips[Demurrage (USD)])',
        f'=IFERROR(SUMIF(Trips[Month],"{m}",Trips[Demurrage (USD)])/COUNTIF(Trips[Month],"{m}"),0)',
    ])

start_m = end_tr + 3
end_m = breakdown_table(
    start_m, 2,
    'BY MONTH (LOADING)',
    ['Month', 'Trips', 'Total Demurrage', 'Avg / Trip'],
    rows_by_month,
)
dash.cell(end_m, 3).value = '=ROWS(Trips[Deal No.])'
dash.cell(end_m, 3).number_format = FMT_INT
dash.cell(end_m, 4).value = '=SUM(Trips[Demurrage (USD)])'
dash.cell(end_m, 4).number_format = FMT_USD
dash.cell(end_m, 5).value = '=IFERROR(SUM(Trips[Demurrage (USD)])/ROWS(Trips[Deal No.]),0)'
dash.cell(end_m, 5).number_format = FMT_USD

# --- TOP 10 DEALS BY DEMURRAGE ---
# Deals sorted by total demurrage (computed in advance)
deal_totals = {}
for t in trips:
    d = t['deal']
    deal_totals[d] = deal_totals.get(d, 0) + (t['demurrage'] or 0)
top_deals = sorted(deal_totals.items(), key=lambda x: -x[1])[:10]
rows_top = []
for d, _ in top_deals:
    rows_top.append([
        d,
        f'=COUNTIF(Trips[Deal No.],{d})',
        f'=SUMIF(Trips[Deal No.],{d},Trips[Demurrage (USD)])',
        f'=IFERROR(SUMIF(Trips[Deal No.],{d},Trips[Demurrage (USD)])/COUNTIF(Trips[Deal No.],{d}),0)',
    ])

start_top = 14
# Place to the right of consignee table (col F)
end_top = breakdown_table(
    start_top, 6,
    'TOP DEALS BY DEMURRAGE',
    ['Deal No.', 'Trips', 'Total Demurrage', 'Avg / Trip'],
    rows_top,
)
dash.cell(end_top, 7).value = '=SUM(G16:G' + str(end_top-1) + ')'
dash.cell(end_top, 7).number_format = FMT_INT
dash.cell(end_top, 8).value = '=SUM(H16:H' + str(end_top-1) + ')'
dash.cell(end_top, 8).number_format = FMT_USD
dash.cell(end_top, 9).value = f'=IFERROR(H{end_top}/G{end_top},0)'
dash.cell(end_top, 9).number_format = FMT_USD

dash.freeze_panes = 'B6'

# === Cover sheet KPI references (point at exact cells) ===
# We need to wire the cover KPIs to actual dashboard cells.
# In dash, KPI USD card is row 6 (title) / 7 (value). For TOTAL DEMURRAGE -> dash!B7
# Let's overwrite the cover KPI value cells with correct references.
cover.cell(27, 2).value = '=Dashboard!B7'
cover.cell(27, 4).value = '=Dashboard!F7&" / "&Dashboard!D7'
cover.cell(27, 6).value = '=Dashboard!D7'
cover.cell(27, 8).value = '=Dashboard!H7'
cover.cell(27, 2).number_format = FMT_USD
cover.cell(27, 4).number_format = '@'
cover.cell(27, 6).number_format = FMT_INT
cover.cell(27, 8).number_format = FMT_USD

# ============================================================
# 6. DEAL STATEMENT (printable per-deal)
# ============================================================
ds = wb.create_sheet('Deal Statement')
ds.sheet_view.showGridLines = False
ds.sheet_view.showRowColHeaders = False

for col, w in zip('ABCDEFGHIJKLM',
                  [2,14,22,12,14,14,14,14,18,14,14,16,2]):
    ds.column_dimensions[col].width = w

# Header band
for r in range(2, 7):
    for c in range(1, 14):
        ds.cell(r, c).fill = fill(NAVY)

ds.merge_cells('B3:L3')
ds.cell(3,2).value = 'DEMURRAGE STATEMENT'
ds.cell(3,2).font = font(size=22, bold=True, color=WHITE)
ds.cell(3,2).alignment = left()

ds.merge_cells('B5:L5')
ds.cell(5,2).value = ('Pick a deal in the gold box below — '
                     'the statement, totals and table refresh automatically.')
ds.cell(5,2).font = font(size=10, italic=True, color=GOLD_LIGHT)
ds.cell(5,2).alignment = left()

for c in range(1, 14):
    ds.cell(7, c).fill = fill(GOLD)
ds.row_dimensions[7].height = 4

# Deal picker
ds.cell(9, 2).value = 'DEAL No.'
ds.cell(9, 2).font = font(size=10, bold=True, color=MUTED)
ds.cell(9, 2).alignment = left()
ds.cell(10, 2).value = deals[0]['deal'] if deals else None
ds.cell(10, 2).font = font(size=18, bold=True, color=NAVY)
ds.cell(10, 2).fill = fill(GOLD_PALE)
ds.cell(10, 2).alignment = center()
ds.cell(10, 2).border = Border(left=medium_gold, right=medium_gold, top=medium_gold, bottom=medium_gold)

# Data validation: allow choosing any deal in Deals table
dv = DataValidation(type='list',
                    formula1=f'=Deals[Deal No.]',
                    allow_blank=False, showDropDown=False)
dv.add('B10')
ds.add_data_validation(dv)

# Statement field helper
def field(row, col, label, value):
    ds.cell(row, col).value = label
    ds.cell(row, col).font = font(size=9, bold=True, color=MUTED)
    ds.cell(row, col).alignment = left()
    ds.cell(row+1, col).value = value
    ds.cell(row+1, col).font = font(size=12, bold=True, color=NAVY)
    ds.cell(row+1, col).alignment = left()
    ds.cell(row+1, col).border = Border(bottom=Side(style='dotted', color=GRAY_RULE))

field(9, 4, 'CONSIGNEE',
      '=IFERROR(VLOOKUP($B$10,Deals[#All],2,FALSE),"")')
field(9, 7, 'ROUTE',
      '=IFERROR(VLOOKUP($B$10,Deals[#All],3,FALSE),"")')
field(9, 10, 'PRODUCT',
      '=IFERROR(VLOOKUP($B$10,Deals[#All],6,FALSE),"")')

field(12, 4, 'LAYTIME (days)',
      '=IFERROR(VLOOKUP($B$10,Deals[#All],7,FALSE),DEF_LAYTIME)')
ds.cell(13, 4).number_format = FMT_INT

field(12, 7, 'RATE (USD/day)',
      '=IFERROR(VLOOKUP($B$10,Deals[#All],8,FALSE),DEF_RATE)')
ds.cell(13, 7).number_format = FMT_USD

field(12, 10, 'PERIOD',
      f'=TEXT(PERIOD_START,"dd-mmm-yyyy")&" → "&TEXT(PERIOD_END,"dd-mmm-yyyy")')

# Big "amount owed" card
ds.merge_cells('B14:C15')
ds.cell(14, 2).value = 'AMOUNT OWED'
ds.cell(14, 2).font = font(size=9, bold=True, color=WHITE)
ds.cell(14, 2).fill = fill(NAVY)
ds.cell(14, 2).alignment = center()
ds.merge_cells('B16:C17')
ds.cell(16, 2).value = '=SUMIF(Trips[Deal No.],$B$10,Trips[Demurrage (USD)])'
ds.cell(16, 2).number_format = FMT_USD
ds.cell(16, 2).font = font(size=22, bold=True, color=NAVY)
ds.cell(16, 2).alignment = center()
ds.cell(16, 2).fill = fill(GOLD_PALE)
for rr in range(14, 18):
    for cc in range(2, 4):
        ds.cell(rr, cc).border = Border(
            left=Side(style='thin', color=GOLD),
            right=Side(style='thin', color=GOLD),
            top=Side(style='thin', color=GOLD),
            bottom=Side(style='thin', color=GOLD),
        )

# Trip count and in-demurrage card
ds.cell(14, 5).value = 'TRIPS'
ds.cell(14, 5).font = font(size=9, bold=True, color=MUTED)
ds.cell(14, 5).alignment = left()
ds.cell(15, 5).value = '=COUNTIF(Trips[Deal No.],$B$10)'
ds.cell(15, 5).font = font(size=20, bold=True, color=NAVY)

ds.cell(14, 8).value = 'IN DEMURRAGE'
ds.cell(14, 8).font = font(size=9, bold=True, color=MUTED)
ds.cell(14, 8).alignment = left()
ds.cell(15, 8).value = ('=COUNTIFS(Trips[Deal No.],$B$10,Trips[Status],"DEMURRAGE")'
                       '&" / "&COUNTIF(Trips[Deal No.],$B$10)')
ds.cell(15, 8).font = font(size=20, bold=True, color=NAVY)

ds.cell(14, 11).value = 'AVG / TRIP'
ds.cell(14, 11).font = font(size=9, bold=True, color=MUTED)
ds.cell(14, 11).alignment = left()
ds.cell(15, 11).value = ('=IFERROR(SUMIF(Trips[Deal No.],$B$10,Trips[Demurrage (USD)])'
                        '/COUNTIF(Trips[Deal No.],$B$10),0)')
ds.cell(15, 11).font = font(size=20, bold=True, color=NAVY)
ds.cell(15, 11).number_format = FMT_USD

# Detail table (filtered by deal). Headers row 19.
detail_headers = ['Date Loaded','Truck No.','Trailer','Transporter','Driver',
                  'Arrival','Offloaded','Waiting','Excess','Demurrage (USD)']
hdr_row = 19
for i, h in enumerate(detail_headers):
    c = ds.cell(hdr_row, 2+i)
    c.value = h
    c.font = font(size=10, bold=True, color=WHITE)
    c.fill = fill(NAVY)
    c.alignment = center(wrap=True)
    c.border = border_all
ds.row_dimensions[hdr_row].height = 32

# We'll fill 50 rows with FILTER-like lookups via INDEX/AGGREGATE so it works on older Excels.
# For maximum robustness we use a per-row "k-th match" pattern:
#   row k: if k <= COUNTIF, return INDEX of the k-th row in Trips where Deal = picked.
N_DETAIL = 40
for k in range(1, N_DETAIL+1):
    r = hdr_row + k
    # k-th matching row index
    base = ('IFERROR(SMALL(IF(Trips[Deal No.]=$B$10,'
            'ROW(Trips[Deal No.])-MIN(ROW(Trips[Deal No.]))+1),{k}),"")').replace('{k}', str(k))
    # We use an INDEX into each column. Wrapping with IFERROR to keep clean.
    def col_formula(trip_col):
        return (f'=IFERROR(INDEX(Trips[{trip_col}],SMALL(IF(Trips[Deal No.]=$B$10,'
                f'ROW(Trips[Deal No.])-MIN(ROW(Trips[Deal No.]))+1),{k})),"")')
    ds.cell(r, 2).value = col_formula('Date Loaded')
    ds.cell(r, 3).value = col_formula('Truck No.')
    ds.cell(r, 4).value = col_formula('Trailer Reg.')
    ds.cell(r, 5).value = col_formula('Transporter')
    ds.cell(r, 6).value = col_formula('Driver')
    ds.cell(r, 7).value = col_formula('Arrival')
    ds.cell(r, 8).value = col_formula('Offloaded')
    ds.cell(r, 9).value = col_formula('Waiting (d)')
    ds.cell(r,10).value = col_formula('Excess (d)')
    ds.cell(r,11).value = col_formula('Demurrage (USD)')

    for j in range(2, 12):
        cc = ds.cell(r, j)
        cc.font = font(size=10)
        cc.border = Border(left=Side(style='thin', color=GRAY_RULE),
                           right=Side(style='thin', color=GRAY_RULE),
                           top=Side(style='thin', color=GRAY_RULE),
                           bottom=Side(style='thin', color=GRAY_RULE))
        cc.alignment = left(indent=1)
        if k % 2 == 0:
            cc.fill = fill(CREAM)
    ds.cell(r, 2).number_format = FMT_DATE
    ds.cell(r, 2).alignment = center()
    ds.cell(r, 7).number_format = FMT_DATE
    ds.cell(r, 7).alignment = center()
    ds.cell(r, 8).number_format = FMT_DATE
    ds.cell(r, 8).alignment = center()
    ds.cell(r, 9).number_format = FMT_INT
    ds.cell(r, 9).alignment = center()
    ds.cell(r,10).number_format = FMT_INT
    ds.cell(r,10).alignment = center()
    ds.cell(r,11).number_format = FMT_USD
    ds.cell(r,11).alignment = right()

# Total row
tot = hdr_row + N_DETAIL + 1
ds.merge_cells(start_row=tot, start_column=2, end_row=tot, end_column=10)
ds.cell(tot, 2).value = 'TOTAL DUE'
ds.cell(tot, 2).font = font(size=12, bold=True, color=WHITE)
ds.cell(tot, 2).fill = fill(NAVY)
ds.cell(tot, 2).alignment = right()
ds.cell(tot,11).value = '=SUMIF(Trips[Deal No.],$B$10,Trips[Demurrage (USD)])'
ds.cell(tot,11).number_format = FMT_USD
ds.cell(tot,11).font = font(size=12, bold=True, color=WHITE)
ds.cell(tot,11).fill = fill(NAVY)
ds.cell(tot,11).alignment = right()
for cc in range(2, 12):
    ds.cell(tot, cc).fill = fill(NAVY)
    ds.cell(tot, cc).font = font(size=12, bold=True, color=WHITE)

# Notes
ds.merge_cells(start_row=tot+3, start_column=2, end_row=tot+3, end_column=11)
ds.cell(tot+3, 2).value = ('NOTES — Demurrage = MAX(0, Waiting − Laytime) × Rate. '
                          'Waiting is measured from Arrival at Offloading to Offloaded date, inclusive of both endpoints.')
ds.cell(tot+3, 2).font = font(size=9, italic=True, color=MUTED)
ds.cell(tot+3, 2).alignment = left(wrap=True)
ds.row_dimensions[tot+3].height = 28

# Conditional formatting on Excess column to highlight outliers
exc_range = f'J{hdr_row+1}:J{hdr_row+N_DETAIL}'
ds.conditional_formatting.add(exc_range,
    FormulaRule(formula=[f'AND(ISNUMBER(J{hdr_row+1}),J{hdr_row+1}>=OUTLIER_DAYS)'],
                fill=fill(RED_BG), font=font(bold=True, color=RED_FG)))

# Print setup: portrait, fit to width
ds.page_setup.orientation = ds.ORIENTATION_LANDSCAPE
ds.page_setup.fitToWidth = 1
ds.sheet_properties.pageSetUpPr.fitToPage = True
ds.print_options.horizontalCentered = True
ds.print_area = f'A1:M{tot+4}'

# ============================================================
# Tab order & colors
# ============================================================
order = ['Cover','Dashboard','Deal Statement','Trips Ledger','Deals','Assumptions']
wb._sheets = [wb[s] for s in order]

color_map = {
    'Cover': NAVY,
    'Dashboard': GOLD,
    'Deal Statement': GOLD,
    'Trips Ledger': NAVY_MID,
    'Deals': NAVY_MID,
    'Assumptions': MUTED,
}
for s, c in color_map.items():
    wb[s].sheet_properties.tabColor = c

# Default sheet on open
wb.active = 0

out = '/home/user/test/DEMURRAGE_TRUCKING_2026_v2.xlsx'
wb.save(out)
print('Saved:', out)
import os
print('Size:', os.path.getsize(out), 'bytes')
