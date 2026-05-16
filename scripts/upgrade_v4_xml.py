"""v4 upgrade: Tier 1 fixes + Payments and EmailLog sheets.

Applied over the v3 output (post macro injection, post button injection),
so we don't disturb drawings or the VBA project.

Changes:
  1. Fix Cover.B25 and Dashboard.B7 demurrage formulas to count only
     trips where Status="DEMURRAGE" (not PENDING/NO DEMURRAGE).
  2. Add Paid (USD) and Outstanding (USD) calculated columns to Claims.
  3. Add new Payments sheet with a Payments table.
  4. Add new EmailLog sheet with an EmailLog table.
  5. Data validation on Claims.Status (drop-down from LIST_Status).
     Data validation on Claims.Currency.
  6. Conditional formatting on Claims:
       - row turns red if Days Overdue > 0
       - status cell colored by value
  7. Extend Claims table from 9 rows to 50 rows so it grows naturally.
"""

from __future__ import annotations
import re
import sys
import zipfile
from copy import deepcopy


# ---------- helpers ----------------------------------------------------

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

CT_WORKSHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
CT_TABLE = "application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"
REL_WORKSHEET = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
REL_TABLE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/table"


def _read_sheet_map(rels: str, wb: str) -> dict[str, tuple[str, str]]:
    """Return {sheet name: (sheet xml path, rid)}."""
    rid_target: dict[str, str] = {}
    for m in re.finditer(r'<Relationship\b(.+?)/>', rels):
        attrs = m.group(1)
        idm = re.search(r'\bId="([^"]+)"', attrs)
        tgt = re.search(r'\bTarget="([^"]+)"', attrs)
        typ = re.search(r'\bType="([^"]+)"', attrs)
        if idm and tgt and typ and typ.group(1).endswith("/worksheet"):
            rid_target[idm.group(1)] = tgt.group(1)
    out: dict[str, tuple[str, str]] = {}
    for m in re.finditer(r'<sheet\b([^/>]+)/>', wb):
        attrs = m.group(1)
        nm = re.search(r'\bname="([^"]+)"', attrs)
        rid = re.search(r'\br:id="([^"]+)"', attrs)
        if nm and rid and rid.group(1) in rid_target:
            out[nm.group(1)] = ("xl/" + rid_target[rid.group(1)], rid.group(1))
    return out


def _max_rid(rels: str) -> int:
    """Return the highest rIdN found in a rels XML."""
    n = 0
    for m in re.finditer(r'Id="rId(\d+)"', rels):
        n = max(n, int(m.group(1)))
    return n


def _max_sheet_id(wb: str) -> int:
    n = 0
    for m in re.finditer(r'\bsheetId="(\d+)"', wb):
        n = max(n, int(m.group(1)))
    return n


def _table_max_id(files: dict[str, bytes]) -> int:
    n = 0
    for name in files:
        if name.startswith("xl/tables/") and name.endswith(".xml"):
            x = files[name].decode("utf-8")
            m = re.search(r'<table[^>]*\bid="(\d+)"', x)
            if m:
                n = max(n, int(m.group(1)))
    return n


# ---------- sheet content for the new sheets ---------------------------

def _payments_sheet_xml() -> str:
    """Build the sheet XML for the Payments sheet."""
    # Headers in B5:H5, table B5:H45 (with totals row included via
    # totalsRowShown=0, just data rows).  Row 2 = nav, row 3 = title.
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS_MAIN}"
           xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
           xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
           xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
           mc:Ignorable="xr">
  <sheetPr><tabColor rgb="FF047857"/></sheetPr>
  <dimension ref="B2:H45"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>
    <col min="2" max="2" width="14" customWidth="1"/>
    <col min="3" max="3" width="30" customWidth="1"/>
    <col min="4" max="4" width="22" customWidth="1"/>
    <col min="5" max="5" width="16" customWidth="1"/>
    <col min="6" max="6" width="10" customWidth="1"/>
    <col min="7" max="7" width="20" customWidth="1"/>
    <col min="8" max="8" width="36" customWidth="1"/>
  </cols>
  <sheetData>
    <row r="3" spans="2:8"><c r="B3" t="inlineStr"><is><t>PAYMENTS LEDGER</t></is></c></row>
    <row r="4" spans="2:8"><c r="B4" t="inlineStr"><is><t>One row per incoming SWIFT. Allocate against a claim by typing its Claim No. in column F.</t></is></c></row>
    <row r="5" spans="2:8">
      <c r="B5" t="inlineStr"><is><t>Payment Date</t></is></c>
      <c r="C5" t="inlineStr"><is><t>Consignee</t></is></c>
      <c r="D5" t="inlineStr"><is><t>SWIFT Ref</t></is></c>
      <c r="E5" t="inlineStr"><is><t>Amount</t></is></c>
      <c r="F5" t="inlineStr"><is><t>Currency</t></is></c>
      <c r="G5" t="inlineStr"><is><t>Claim No.</t></is></c>
      <c r="H5" t="inlineStr"><is><t>Notes</t></is></c>
    </row>
  </sheetData>
  <pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>
  <tableParts count="1"><tablePart r:id="rId1"/></tableParts>
</worksheet>'''


def _emaillog_sheet_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS_MAIN}"
           xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
           xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
           xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
           mc:Ignorable="xr">
  <sheetPr><tabColor rgb="FF1F4E79"/></sheetPr>
  <dimension ref="B2:H45"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>
    <col min="2" max="2" width="20" customWidth="1"/>
    <col min="3" max="3" width="14" customWidth="1"/>
    <col min="4" max="4" width="22" customWidth="1"/>
    <col min="5" max="5" width="28" customWidth="1"/>
    <col min="6" max="6" width="28" customWidth="1"/>
    <col min="7" max="7" width="42" customWidth="1"/>
    <col min="8" max="8" width="40" customWidth="1"/>
  </cols>
  <sheetData>
    <row r="3" spans="2:8"><c r="B3" t="inlineStr"><is><t>EMAIL LOG</t></is></c></row>
    <row r="4" spans="2:8"><c r="B4" t="inlineStr"><is><t>Every Outlook draft opened by EmailClaim or SendReminders is logged here.</t></is></c></row>
    <row r="5" spans="2:8">
      <c r="B5" t="inlineStr"><is><t>Timestamp</t></is></c>
      <c r="C5" t="inlineStr"><is><t>User</t></is></c>
      <c r="D5" t="inlineStr"><is><t>Claim No.</t></is></c>
      <c r="E5" t="inlineStr"><is><t>To</t></is></c>
      <c r="F5" t="inlineStr"><is><t>Cc</t></is></c>
      <c r="G5" t="inlineStr"><is><t>Subject</t></is></c>
      <c r="H5" t="inlineStr"><is><t>Attachment</t></is></c>
    </row>
  </sheetData>
  <pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>
  <tableParts count="1"><tablePart r:id="rId1"/></tableParts>
</worksheet>'''


def _payments_table_xml(table_id: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<table xmlns="{NS_MAIN}"
       id="{table_id}" name="Payments" displayName="Payments"
       ref="B5:H45" totalsRowShown="0">
  <autoFilter ref="B5:H45"/>
  <tableColumns count="7">
    <tableColumn id="1" name="Payment Date"/>
    <tableColumn id="2" name="Consignee"/>
    <tableColumn id="3" name="SWIFT Ref"/>
    <tableColumn id="4" name="Amount"/>
    <tableColumn id="5" name="Currency"/>
    <tableColumn id="6" name="Claim No."/>
    <tableColumn id="7" name="Notes"/>
  </tableColumns>
  <tableStyleInfo name="TableStyleLight15" showFirstColumn="0" showLastColumn="0"
                  showRowStripes="1" showColumnStripes="0"/>
</table>'''


def _emaillog_table_xml(table_id: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<table xmlns="{NS_MAIN}"
       id="{table_id}" name="EmailLog" displayName="EmailLog"
       ref="B5:H45" totalsRowShown="0">
  <autoFilter ref="B5:H45"/>
  <tableColumns count="7">
    <tableColumn id="1" name="Timestamp"/>
    <tableColumn id="2" name="User"/>
    <tableColumn id="3" name="Claim No."/>
    <tableColumn id="4" name="To"/>
    <tableColumn id="5" name="Cc"/>
    <tableColumn id="6" name="Subject"/>
    <tableColumn id="7" name="Attachment"/>
  </tableColumns>
  <tableStyleInfo name="TableStyleLight15" showFirstColumn="0" showLastColumn="0"
                  showRowStripes="1" showColumnStripes="0"/>
</table>'''


def _sheet_rel_xml(table_filename: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="{REL_TABLE}" Target="../tables/{table_filename}"/>
</Relationships>'''


# ---------- main -------------------------------------------------------

def upgrade(src: str, dst: str) -> None:
    with zipfile.ZipFile(src, "r") as zin:
        files: dict[str, bytes] = {n: zin.read(n) for n in zin.namelist()}

    wb_xml  = files["xl/workbook.xml"].decode("utf-8")
    rels    = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    sheets  = _read_sheet_map(rels, wb_xml)

    # ----- 1. Fix Cover and Dashboard demurrage totals -----
    cover_path = sheets["Cover"][0]
    cv = files[cover_path].decode("utf-8")
    cv = cv.replace(
        "SUM(Trips[Demurrage (USD)])",
        'SUMIFS(Trips[Demurrage (USD)],Trips[Status],"DEMURRAGE")',
    )
    files[cover_path] = cv.encode("utf-8")

    dash_path = sheets["Dashboard"][0]
    dv = files[dash_path].decode("utf-8")
    dv = dv.replace(
        "SUM(Trips[Demurrage (USD)])",
        'SUMIFS(Trips[Demurrage (USD)],Trips[Status],"DEMURRAGE")',
    )
    files[dash_path] = dv.encode("utf-8")

    # ----- 2. Extend Claims table to 50 rows and add Paid/Outstanding columns -----
    # Find Claims table xml
    claims_table_path = None
    for n in files:
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            if b'displayName="Claims"' in files[n]:
                claims_table_path = n
                break
    if claims_table_path is None:
        raise RuntimeError("Claims table not found")
    ct = files[claims_table_path].decode("utf-8")

    # Add Paid (USD) and Outstanding (USD) columns if not already present.
    if "Paid (USD)" not in ct:
        # The original ref is something like B6:R16.  We extend to B6:T56
        # to add S and T columns and 41 additional data rows.
        ct = re.sub(r'ref="B6:R\d+"', 'ref="B6:T56"', ct)
        ct = re.sub(r'(<autoFilter\s+ref=")B6:R\d+(")', r'\g<1>B6:T55\g<2>', ct)
        # Bump tableColumns count: was 17.
        ct = re.sub(r'(<tableColumns[^>]*\bcount=")17(")', r'\g<1>19\g<2>', ct)
        # Append two new columns after the existing last one (id=1, "Actions").
        # Use higher ids.
        new_cols = (
            '<tableColumn id="201" name="Paid (USD)">'
            '<calculatedColumnFormula>IFERROR(SUMIFS(Payments[Amount],Payments[Claim No.],Claims[[#This Row],[Claim No.]]),0)</calculatedColumnFormula>'
            '</tableColumn>'
            '<tableColumn id="202" name="Outstanding (USD)">'
            '<calculatedColumnFormula>Claims[[#This Row],[Amount (USD)]]-Claims[[#This Row],[Paid (USD)]]</calculatedColumnFormula>'
            '</tableColumn>'
        )
        ct = ct.replace("</tableColumns>", new_cols + "</tableColumns>")
        files[claims_table_path] = ct.encode("utf-8")

    # ----- 3. Extend Claims sheet: rewrite range, add header cells for S5/T5,
    #         add a few empty rows past row 15 so the table absorbs growth. -----
    claims_path = sheets["Claims"][0]
    csx = files[claims_path].decode("utf-8")
    # Add header cells S6 and T6.
    csx = re.sub(
        r'(<c r="R6"[^>]*(?:/>|>.*?</c>))',
        r'\g<1><c r="S6" t="inlineStr"><is><t>Paid (USD)</t></is></c><c r="T6" t="inlineStr"><is><t>Outstanding (USD)</t></is></c>',
        csx, count=1, flags=re.DOTALL,
    )
    # Update dimension if present
    csx = re.sub(r'<dimension ref="B\d+:R\d+"', '<dimension ref="B2:T56"', csx)
    files[claims_path] = csx.encode("utf-8")

    # ----- 4. Data validation on Claims.Status (L7:L55) and Currency (K7:K55) -----
    csx = files[claims_path].decode("utf-8")
    if "<dataValidations" not in csx:
        dv_block = (
            '<dataValidations count="2">'
            '<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="L7:L55">'
            '<formula1>"Draft,Sent,Partial,Paid,Cancelled"</formula1>'
            '</dataValidation>'
            '<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="K7:K55">'
            '<formula1>"USD,EUR,ZMW,ZAR"</formula1>'
            '</dataValidation>'
            '</dataValidations>'
        )
        # Insert before <pageMargins> or before </worksheet>.
        if '<pageMargins' in csx:
            csx = csx.replace('<pageMargins', dv_block + '<pageMargins', 1)
        else:
            csx = csx.replace('</worksheet>', dv_block + '</worksheet>', 1)
        files[claims_path] = csx.encode("utf-8")

    # ----- 5. Conditional formatting on Claims: red row when Days Overdue > 0 -----
    csx = files[claims_path].decode("utf-8")
    if 'type="expression"' not in csx:
        # We need a dxf style first.  Add dxf to styles.xml.
        styles_path = "xl/styles.xml"
        sx = files[styles_path].decode("utf-8")
        dxf_block_red = (
            '<dxf>'
            '<font><color rgb="FF9C0006"/></font>'
            '<fill><patternFill><bgColor rgb="FFFFC7CE"/></patternFill></fill>'
            '</dxf>'
        )
        dxf_block_amber = (
            '<dxf>'
            '<font><color rgb="FF9C5700"/></font>'
            '<fill><patternFill><bgColor rgb="FFFFEB9C"/></patternFill></fill>'
            '</dxf>'
        )
        dxf_block_green = (
            '<dxf>'
            '<font><color rgb="FF006100"/></font>'
            '<fill><patternFill><bgColor rgb="FFC6EFCE"/></patternFill></fill>'
            '</dxf>'
        )
        # Count existing dxfs to know the indices we'll get.
        m_dxfs = re.search(r'<dxfs\s+count="(\d+)"\s*>(.*?)</dxfs>', sx, re.DOTALL)
        if m_dxfs:
            existing_count = int(m_dxfs.group(1))
            new_count = existing_count + 3
            replacement = (
                f'<dxfs count="{new_count}">'
                f'{m_dxfs.group(2)}'
                f'{dxf_block_red}{dxf_block_amber}{dxf_block_green}'
                f'</dxfs>'
            )
            sx = sx[:m_dxfs.start()] + replacement + sx[m_dxfs.end():]
            red_idx = existing_count
            amber_idx = existing_count + 1
            green_idx = existing_count + 2
        else:
            sx = sx.replace(
                '</styleSheet>',
                f'<dxfs count="3">{dxf_block_red}{dxf_block_amber}{dxf_block_green}</dxfs></styleSheet>',
            )
            red_idx, amber_idx, green_idx = 0, 1, 2
        files[styles_path] = sx.encode("utf-8")

        # Conditional formatting block in the Claims sheet.
        cf = (
            f'<conditionalFormatting sqref="B7:T55">'
            f'<cfRule type="expression" dxfId="{red_idx}" priority="1">'
            f'<formula>AND($L7="Sent",ISNUMBER($O7),$O7&gt;0)</formula>'
            f'</cfRule>'
            f'<cfRule type="expression" dxfId="{green_idx}" priority="2">'
            f'<formula>$L7="Paid"</formula>'
            f'</cfRule>'
            f'<cfRule type="expression" dxfId="{amber_idx}" priority="3">'
            f'<formula>$L7="Partial"</formula>'
            f'</cfRule>'
            f'</conditionalFormatting>'
        )
        # Insert before <dataValidations> or <pageMargins>.
        for anchor in ('<dataValidations', '<pageMargins', '</worksheet>'):
            if anchor in csx:
                csx = csx.replace(anchor, cf + anchor, 1)
                break
        files[claims_path] = csx.encode("utf-8")

    # ----- 6. Trips Ledger: amber conditional formatting on outlier waiting days -----
    trips_path = sheets["Trips Ledger"][0]
    tx = files[trips_path].decode("utf-8")
    if 'type="cellIs" operator="greaterThan"' not in tx:
        # Use an existing dxf index — we'll add one.  Reuse the amber from styles.
        # For simplicity reuse our amber index from earlier (need to recompute):
        # parse from styles.xml again.
        styles_path = "xl/styles.xml"
        sx = files[styles_path].decode("utf-8")
        m_dxfs = re.search(r'<dxfs\s+count="(\d+)"', sx)
        if m_dxfs:
            total = int(m_dxfs.group(1))
            amber_idx = total - 2  # we appended red, amber, green; amber is 2nd of those
        else:
            amber_idx = 1
        # Column O = Waiting (d), rows 7:507 in Trips Ledger.
        cf_trips = (
            f'<conditionalFormatting sqref="O7:O507">'
            f'<cfRule type="cellIs" operator="greaterThan" dxfId="{amber_idx}" priority="1">'
            f'<formula>OUTLIER_DAYS</formula>'
            f'</cfRule>'
            f'</conditionalFormatting>'
        )
        for anchor in ('<dataValidations', '<pageMargins', '</worksheet>'):
            if anchor in tx:
                tx = tx.replace(anchor, cf_trips + anchor, 1)
                break
        files[trips_path] = tx.encode("utf-8")

    # ----- 7. Add the two new sheets ---------------------------------------
    # Allocate sheet xml filenames and rIds.
    existing_sheet_xmls = sorted(
        n for n in files if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n))
    next_sheet_idx = 1 + max(
        int(re.search(r'sheet(\d+)\.xml', n).group(1)) for n in existing_sheet_xmls)
    next_rid = _max_rid(rels) + 1
    next_sheet_id = _max_sheet_id(wb_xml) + 1
    next_table_id = _table_max_id(files) + 1

    def add_new_sheet(name: str, sheet_xml_str: str,
                      table_xml_str: str, tab_color: str = ""):
        nonlocal next_sheet_idx, next_rid, next_sheet_id, next_table_id, wb_xml, rels
        sheet_filename = f"sheet{next_sheet_idx}.xml"
        table_filename = f"table{next_table_id}.xml"
        sheet_path = f"xl/worksheets/{sheet_filename}"
        sheet_rels_path = f"xl/worksheets/_rels/{sheet_filename}.rels"
        table_path = f"xl/tables/{table_filename}"

        files[sheet_path] = sheet_xml_str.encode("utf-8")
        files[table_path] = table_xml_str.encode("utf-8")
        files[sheet_rels_path] = _sheet_rel_xml(table_filename).encode("utf-8")

        # Workbook rels
        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="rId{next_rid}" Type="{REL_WORKSHEET}" Target="worksheets/{sheet_filename}"/></Relationships>',
        )
        # Workbook sheets
        new_sheet_decl = f'<sheet name="{name}" sheetId="{next_sheet_id}" r:id="rId{next_rid}"/>'
        wb_xml = wb_xml.replace("</sheets>", new_sheet_decl + "</sheets>")
        # Content types
        ctp = files["[Content_Types].xml"].decode("utf-8")
        ctp = ctp.replace(
            "</Types>",
            f'<Override PartName="/{sheet_path}" ContentType="{CT_WORKSHEET}"/>'
            f'<Override PartName="/{table_path}" ContentType="{CT_TABLE}"/>'
            "</Types>",
        )
        files["[Content_Types].xml"] = ctp.encode("utf-8")
        next_sheet_idx += 1
        next_rid += 1
        next_sheet_id += 1
        next_table_id += 1

    if "Payments" not in sheets:
        add_new_sheet(
            "Payments",
            _payments_sheet_xml(),
            _payments_table_xml(next_table_id),
        )
    if "EmailLog" not in sheets:
        add_new_sheet(
            "EmailLog",
            _emaillog_sheet_xml(),
            _emaillog_table_xml(next_table_id),
        )

    files["xl/workbook.xml"] = wb_xml.encode("utf-8")
    files["xl/_rels/workbook.xml.rels"] = rels.encode("utf-8")

    # ----- write -----
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: upgrade_v4_xml.py <in.xlsm> <out.xlsm>", file=sys.stderr)
        sys.exit(2)
    upgrade(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]}")
