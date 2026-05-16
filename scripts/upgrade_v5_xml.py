"""v5 upgrade: remaining Tier 2 items.

Applied AFTER v4_xml so column / row indices align with what v4 produced.

Changes:
  1. Consignees table on Company gets 5 new columns:
       Credit Limit (USD), Open Claims (USD), Utilisation, KYC Refresh, Risk Flag
  2. Claims table gets 4 new columns:
       Disputed, Net Claim (USD), FX Rate, USD Equiv
  3. New FX sheet with FX table (Currency, Rate to USD, Last Updated, Notes).
  4. Dashboard:
       - Monthly demurrage helper table (B40:C52) by Month
       - Data bars on existing By Consignee / By Transporter / Aging columns
       - Data bars on the new monthly helper
"""

from __future__ import annotations
import re
import sys
import zipfile

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CT_WORKSHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
CT_TABLE = "application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"
REL_WORKSHEET = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
REL_TABLE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/table"


def _read_sheet_map(rels: str, wb: str) -> dict[str, tuple[str, str]]:
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
    n = 0
    for m in re.finditer(r'Id="rId(\d+)"', rels):
        n = max(n, int(m.group(1)))
    return n


def _max_sheet_id(wb: str) -> int:
    n = 0
    for m in re.finditer(r'\bsheetId="(\d+)"', wb):
        n = max(n, int(m.group(1)))
    return n


def _max_table_id(files: dict[str, bytes]) -> int:
    n = 0
    for name in files:
        if name.startswith("xl/tables/") and name.endswith(".xml"):
            x = files[name].decode("utf-8")
            m = re.search(r'<table[^>]*\bid="(\d+)"', x)
            if m:
                n = max(n, int(m.group(1)))
    return n


def _max_dxf_idx(styles_xml: str) -> int:
    m = re.search(r'<dxfs\s+count="(\d+)"', styles_xml)
    return int(m.group(1)) if m else 0


# ---------- FX sheet ---------------------------------------------------

def _fx_sheet_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS_MAIN}"
           xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
           xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
  <sheetPr><tabColor rgb="FFB45309"/></sheetPr>
  <dimension ref="B2:E12"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>
    <col min="2" max="2" width="14" customWidth="1"/>
    <col min="3" max="3" width="16" customWidth="1"/>
    <col min="4" max="4" width="16" customWidth="1"/>
    <col min="5" max="5" width="36" customWidth="1"/>
  </cols>
  <sheetData>
    <row r="3" spans="2:5"><c r="B3" t="inlineStr"><is><t>FX RATES</t></is></c></row>
    <row r="4" spans="2:5"><c r="B4" t="inlineStr"><is><t>Single latest rate per currency. Update Rate to USD when it moves materially.</t></is></c></row>
    <row r="6" spans="2:5">
      <c r="B6" t="inlineStr"><is><t>Currency</t></is></c>
      <c r="C6" t="inlineStr"><is><t>Rate to USD</t></is></c>
      <c r="D6" t="inlineStr"><is><t>Last Updated</t></is></c>
      <c r="E6" t="inlineStr"><is><t>Notes</t></is></c>
    </row>
    <row r="7"><c r="B7" t="inlineStr"><is><t>USD</t></is></c><c r="C7"><v>1</v></c></row>
    <row r="8"><c r="B8" t="inlineStr"><is><t>EUR</t></is></c><c r="C8"><v>1.08</v></c></row>
    <row r="9"><c r="B9" t="inlineStr"><is><t>ZAR</t></is></c><c r="C9"><v>0.055</v></c></row>
    <row r="10"><c r="B10" t="inlineStr"><is><t>ZMW</t></is></c><c r="C10"><v>0.045</v></c></row>
    <row r="11"><c r="B11" t="inlineStr"><is><t>MZN</t></is></c><c r="C11"><v>0.0156</v></c></row>
    <row r="12"><c r="B12" t="inlineStr"><is><t>BWP</t></is></c><c r="C12"><v>0.073</v></c></row>
  </sheetData>
  <pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>
  <tableParts count="1"><tablePart r:id="rId1"/></tableParts>
</worksheet>'''


def _fx_table_xml(table_id: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<table xmlns="{NS_MAIN}"
       id="{table_id}" name="FX" displayName="FX"
       ref="B6:E12" totalsRowShown="0">
  <autoFilter ref="B6:E12"/>
  <tableColumns count="4">
    <tableColumn id="1" name="Currency"/>
    <tableColumn id="2" name="Rate to USD"/>
    <tableColumn id="3" name="Last Updated"/>
    <tableColumn id="4" name="Notes"/>
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

    wb_xml = files["xl/workbook.xml"].decode("utf-8")
    rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    sheets = _read_sheet_map(rels, wb_xml)

    # ===== 1. Extend Consignees table on Company ===========================
    # Find Consignees table xml.
    consignees_path = None
    for n in files:
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            if b'displayName="Consignees"' in files[n]:
                consignees_path = n
                break
    if consignees_path is None:
        raise RuntimeError("Consignees table not found")
    ctx = files[consignees_path].decode("utf-8")

    if "Credit Limit (USD)" not in ctx:
        # ref was B30:E33, count=4. Extend to B30:J33, count=9.
        ctx = re.sub(r'ref="B30:E33"', 'ref="B30:J33"', ctx)
        ctx = re.sub(r'(<autoFilter\s+ref=")B30:E33(")', r'\g<1>B30:J33\g<2>', ctx)
        ctx = re.sub(r'(<tableColumns[^>]*\bcount=")4(")', r'\g<1>9\g<2>', ctx)
        new_cols = (
            '<tableColumn id="50" name="Credit Limit (USD)"/>'
            '<tableColumn id="51" name="Open Claims (USD)">'
            '<calculatedColumnFormula>'
            'IFERROR(SUMPRODUCT('
            '(Claims[Consignee]=Consignees[[#This Row],[Consignee]])*'
            '(Claims[Outstanding (USD)])*'
            '((Claims[Status]="Sent")+(Claims[Status]="Partial"))'
            '),0)'
            '</calculatedColumnFormula>'
            '</tableColumn>'
            '<tableColumn id="52" name="Utilisation">'
            '<calculatedColumnFormula>'
            'IFERROR(Consignees[[#This Row],[Open Claims (USD)]]/Consignees[[#This Row],[Credit Limit (USD)]],0)'
            '</calculatedColumnFormula>'
            '</tableColumn>'
            '<tableColumn id="53" name="KYC Refresh"/>'
            '<tableColumn id="54" name="Risk Flag"/>'
        )
        ctx = ctx.replace("</tableColumns>", new_cols + "</tableColumns>")
        files[consignees_path] = ctx.encode("utf-8")

    # Add the header cells F30..J30 on Company.
    co_path = sheets["Company"][0]
    cox = files[co_path].decode("utf-8")
    if 'r="F30"' not in cox:
        # Anchor on E30 (Cc Emails) cell to insert after it.
        # E30 is "<c r=\"E30\" t=\"inlineStr\"><is><t>Cc Emails</t></is></c>"
        ins = (
            '<c r="F30" t="inlineStr"><is><t>Credit Limit (USD)</t></is></c>'
            '<c r="G30" t="inlineStr"><is><t>Open Claims (USD)</t></is></c>'
            '<c r="H30" t="inlineStr"><is><t>Utilisation</t></is></c>'
            '<c r="I30" t="inlineStr"><is><t>KYC Refresh</t></is></c>'
            '<c r="J30" t="inlineStr"><is><t>Risk Flag</t></is></c>'
        )
        cox = re.sub(
            r'(<c r="E30"[^>]*>.*?</c>)',
            r'\g<1>' + ins,
            cox, count=1, flags=re.DOTALL,
        )
        files[co_path] = cox.encode("utf-8")

    # ===== 2. Extend Claims table with dispute + FX columns ================
    claims_table_path = None
    for n in files:
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            if b'displayName="Claims"' in files[n]:
                claims_table_path = n
                break
    if claims_table_path is None:
        raise RuntimeError("Claims table not found")
    clt = files[claims_table_path].decode("utf-8")

    if "Disputed" not in clt:
        # ref was B6:T56, count=19. Extend to B6:X56, count=23.
        clt = re.sub(r'ref="B6:T56"', 'ref="B6:X56"', clt)
        clt = re.sub(r'(<autoFilter\s+ref=")B6:T55(")', r'\g<1>B6:X55\g<2>', clt)
        clt = re.sub(r'(<tableColumns[^>]*\bcount=")19(")', r'\g<1>23\g<2>', clt)
        new_cols = (
            '<tableColumn id="301" name="Disputed"/>'
            '<tableColumn id="302" name="Net Claim (USD)">'
            '<calculatedColumnFormula>'
            'IF(Claims[[#This Row],[Disputed]]="Y",'
            'Claims[[#This Row],[Amount (USD)]],'
            'Claims[[#This Row],[Amount (USD)]])'
            '</calculatedColumnFormula>'
            '</tableColumn>'
            '<tableColumn id="303" name="FX Rate">'
            '<calculatedColumnFormula>'
            'IFERROR(VLOOKUP(Claims[[#This Row],[Currency]],FX[],2,FALSE),1)'
            '</calculatedColumnFormula>'
            '</tableColumn>'
            '<tableColumn id="304" name="USD Equiv">'
            '<calculatedColumnFormula>'
            'Claims[[#This Row],[Net Claim (USD)]]*Claims[[#This Row],[FX Rate]]'
            '</calculatedColumnFormula>'
            '</tableColumn>'
        )
        clt = clt.replace("</tableColumns>", new_cols + "</tableColumns>")
        files[claims_table_path] = clt.encode("utf-8")

        # Add Claims header cells U6..X6.
        claims_path = sheets["Claims"][0]
        csx = files[claims_path].decode("utf-8")
        ins = (
            '<c r="U6" t="inlineStr"><is><t>Disputed</t></is></c>'
            '<c r="V6" t="inlineStr"><is><t>Net Claim (USD)</t></is></c>'
            '<c r="W6" t="inlineStr"><is><t>FX Rate</t></is></c>'
            '<c r="X6" t="inlineStr"><is><t>USD Equiv</t></is></c>'
        )
        csx = re.sub(
            r'(<c r="T6"[^>]*>.*?</c>)',
            r'\g<1>' + ins,
            csx, count=1, flags=re.DOTALL,
        )
        # Update conditional formatting range from B7:T55 to B7:X55.
        csx = csx.replace('sqref="B7:T55"', 'sqref="B7:X55"')
        # Update dimension
        csx = re.sub(r'<dimension ref="B2:T56"', '<dimension ref="B2:X56"', csx)
        # Add data validation for Disputed (U) with Y/N list.
        if 'sqref="U7:U55"' not in csx:
            new_dv = (
                '<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="U7:U55">'
                '<formula1>"Y,N"</formula1>'
                '</dataValidation>'
            )
            # Find the existing <dataValidations count="N"> and bump count + append.
            m_dv = re.search(r'<dataValidations\s+count="(\d+)">', csx)
            if m_dv:
                new_count = int(m_dv.group(1)) + 1
                csx = csx.replace(
                    m_dv.group(0), f'<dataValidations count="{new_count}">', 1)
                csx = csx.replace(
                    '</dataValidations>', new_dv + '</dataValidations>', 1)
        files[claims_path] = csx.encode("utf-8")

    # ===== 3. Add FX sheet ================================================
    if "FX" not in sheets:
        next_sheet_idx = 1 + max(
            int(re.search(r'sheet(\d+)\.xml', n).group(1))
            for n in files if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)
        )
        next_rid = _max_rid(rels) + 1
        next_sheet_id = _max_sheet_id(wb_xml) + 1
        next_table_id = _max_table_id(files) + 1

        sheet_filename = f"sheet{next_sheet_idx}.xml"
        table_filename = f"table{next_table_id}.xml"
        sheet_path = f"xl/worksheets/{sheet_filename}"
        sheet_rels_path = f"xl/worksheets/_rels/{sheet_filename}.rels"
        table_path = f"xl/tables/{table_filename}"

        files[sheet_path] = _fx_sheet_xml().encode("utf-8")
        files[table_path] = _fx_table_xml(next_table_id).encode("utf-8")
        files[sheet_rels_path] = _sheet_rel_xml(table_filename).encode("utf-8")

        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="rId{next_rid}" Type="{REL_WORKSHEET}" Target="worksheets/{sheet_filename}"/></Relationships>',
        )
        new_sheet_decl = f'<sheet name="FX" sheetId="{next_sheet_id}" r:id="rId{next_rid}"/>'
        wb_xml = wb_xml.replace("</sheets>", new_sheet_decl + "</sheets>")

        ctp = files["[Content_Types].xml"].decode("utf-8")
        ctp = ctp.replace(
            "</Types>",
            f'<Override PartName="/{sheet_path}" ContentType="{CT_WORKSHEET}"/>'
            f'<Override PartName="/{table_path}" ContentType="{CT_TABLE}"/>'
            "</Types>",
        )
        files["[Content_Types].xml"] = ctp.encode("utf-8")

    # ===== 4. Dashboard upgrades: monthly helper + data bars ==============
    dash_path = sheets["Dashboard"][0]
    dx = files[dash_path].decode("utf-8")

    # Dashboard already has a "BY MONTH" dynamic-array section at B37:D41
    # (months / trips / demurrage).  We don't add a duplicate helper -- we
    # just attach data bars to the existing aggregations, including the
    # monthly demurrage column with extra buffer rows for spillover.
    if 'type="dataBar"' not in dx:
        cf_block = (
            '<conditionalFormatting sqref="D17:D24">'
            '<cfRule type="dataBar" priority="100"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FF5B9BD5"/></dataBar></cfRule>'
            '</conditionalFormatting>'
            '<conditionalFormatting sqref="D27:D34">'
            '<cfRule type="dataBar" priority="101"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FF70AD47"/></dataBar></cfRule>'
            '</conditionalFormatting>'
            '<conditionalFormatting sqref="H30:H34">'
            '<cfRule type="dataBar" priority="102"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FFED7D31"/></dataBar></cfRule>'
            '</conditionalFormatting>'
            '<conditionalFormatting sqref="I16:I24">'
            '<cfRule type="dataBar" priority="103"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FF7030A0"/></dataBar></cfRule>'
            '</conditionalFormatting>'
            '<conditionalFormatting sqref="D37:D49">'
            '<cfRule type="dataBar" priority="104"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FFFF9F1C"/></dataBar></cfRule>'
            '</conditionalFormatting>'
        )
        for anchor in ('<pageMargins', '<drawing ', '</worksheet>'):
            if anchor in dx:
                dx = dx.replace(anchor, cf_block + anchor, 1)
                break
    files[dash_path] = dx.encode("utf-8")

    # Write workbook.xml + rels (they may have been touched if FX added).
    files["xl/workbook.xml"] = wb_xml.encode("utf-8")
    files["xl/_rels/workbook.xml.rels"] = rels.encode("utf-8")

    # ----- write -----
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: upgrade_v5_xml.py <in.xlsm> <out.xlsm>", file=sys.stderr)
        sys.exit(2)
    upgrade(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]}")
