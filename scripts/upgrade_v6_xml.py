"""v6 upgrade: Tier 3 items.

Applied AFTER v5_xml.

Changes:
  1. Deals: add 'Despatch Rate (USD/day)' column.
  2. Trips: add 'Despatch (d)' and 'Despatch (USD)' calculated columns.
  3. Claims: add 'Issuer' column (drop-down from new Entities table).
  4. New Statement sheet with consignee drop-down + Generate Statement button.
  5. Add an Entities section on Company (B36+) so multi-entity issuance is
     possible later -- structural prep only; full per-entity Invoice
     templating is a follow-up.
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


def _read_sheet_map(rels: str, wb: str) -> dict[str, str]:
    rid_target: dict[str, str] = {}
    for m in re.finditer(r'<Relationship\b(.+?)/>', rels):
        attrs = m.group(1)
        idm = re.search(r'\bId="([^"]+)"', attrs)
        tgt = re.search(r'\bTarget="([^"]+)"', attrs)
        typ = re.search(r'\bType="([^"]+)"', attrs)
        if idm and tgt and typ and typ.group(1).endswith("/worksheet"):
            rid_target[idm.group(1)] = tgt.group(1)
    out: dict[str, str] = {}
    for m in re.finditer(r'<sheet\b([^/>]+)/>', wb):
        attrs = m.group(1)
        nm = re.search(r'\bname="([^"]+)"', attrs)
        rid = re.search(r'\br:id="([^"]+)"', attrs)
        if nm and rid and rid.group(1) in rid_target:
            out[nm.group(1)] = "xl/" + rid_target[rid.group(1)]
    return out


def _max_rid(rels: str) -> int:
    return max((int(m.group(1)) for m in re.finditer(r'Id="rId(\d+)"', rels)), default=0)


def _max_sheet_id(wb: str) -> int:
    return max((int(m.group(1)) for m in re.finditer(r'\bsheetId="(\d+)"', wb)), default=0)


def _max_table_id(files: dict[str, bytes]) -> int:
    n = 0
    for name in files:
        if name.startswith("xl/tables/") and name.endswith(".xml"):
            x = files[name].decode("utf-8")
            m = re.search(r'<table[^>]*\bid="(\d+)"', x)
            if m:
                n = max(n, int(m.group(1)))
    return n


# ---------- Statement sheet --------------------------------------------

def _statement_sheet_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS_MAIN}"
           xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
           xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
  <sheetPr><tabColor rgb="FFB45309"/></sheetPr>
  <dimension ref="B2:K200"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>
    <col min="2" max="2" width="16" customWidth="1"/>
    <col min="3" max="3" width="22" customWidth="1"/>
    <col min="4" max="4" width="14" customWidth="1"/>
    <col min="5" max="5" width="14" customWidth="1"/>
    <col min="6" max="6" width="14" customWidth="1"/>
    <col min="7" max="7" width="14" customWidth="1"/>
    <col min="8" max="8" width="14" customWidth="1"/>
    <col min="9" max="9" width="12" customWidth="1"/>
    <col min="10" max="10" width="12" customWidth="1"/>
  </cols>
  <sheetData>
    <row r="2" spans="2:10"><c r="B2" t="inlineStr"><is><t>STATEMENT OF ACCOUNT</t></is></c></row>
    <row r="3" spans="2:10">
      <c r="B3" t="inlineStr"><is><t>Consignee:</t></is></c>
      <c r="C3" t="inlineStr"><is><t></t></is></c>
    </row>
    <row r="4" spans="2:10">
      <c r="B4" t="inlineStr"><is><t>Pick a consignee from the drop-down on C3, then click 'Generate Statement' (button at top-right) or run GenerateStatement from Alt+F8.</t></is></c>
    </row>
  </sheetData>
  <dataValidations count="1">
    <dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="C3">
      <formula1>=Consignees[Consignee]</formula1>
    </dataValidation>
  </dataValidations>
  <pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>
  <pageSetup orientation="portrait" paperSize="9" fitToHeight="0"/>
</worksheet>'''


def _sheet_rel_xml_no_table() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>'''


# ---------- main -------------------------------------------------------

def upgrade(src: str, dst: str) -> None:
    with zipfile.ZipFile(src, "r") as zin:
        files: dict[str, bytes] = {n: zin.read(n) for n in zin.namelist()}

    wb_xml = files["xl/workbook.xml"].decode("utf-8")
    rels   = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    sheets = _read_sheet_map(rels, wb_xml)

    # ===== 1. Deals: add Despatch Rate column ============================
    deals_table_path = None
    for n in files:
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            if b'displayName="Deals"' in files[n]:
                deals_table_path = n
                break
    if deals_table_path is None:
        raise RuntimeError("Deals table not found")
    dt = files[deals_table_path].decode("utf-8")
    if "Despatch Rate" not in dt:
        dt = re.sub(r'ref="B6:K30"', 'ref="B6:L30"', dt)
        dt = re.sub(r'(<autoFilter\s+ref=")B6:K30(")', r'\g<1>B6:L30\g<2>', dt)
        dt = re.sub(r'(<tableColumns[^>]*\bcount=")10(")', r'\g<1>11\g<2>', dt)
        new_col = '<tableColumn id="400" name="Despatch Rate (USD/day)"/>'
        dt = dt.replace("</tableColumns>", new_col + "</tableColumns>")
        files[deals_table_path] = dt.encode("utf-8")

        # Header cell L6 in Deals sheet
        deals_path = sheets["Deals"]
        ds = files[deals_path].decode("utf-8")
        ds = re.sub(
            r'(<c r="K6"[^>]*>.*?</c>)',
            r'\g<1><c r="L6" t="inlineStr"><is><t>Despatch Rate (USD/day)</t></is></c>',
            ds, count=1, flags=re.DOTALL,
        )
        files[deals_path] = ds.encode("utf-8")

    # ===== 2. Trips: add Despatch (d) + Despatch (USD) ===================
    trips_table_path = None
    for n in files:
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            if b'displayName="Trips"' in files[n]:
                trips_table_path = n
                break
    if trips_table_path is None:
        raise RuntimeError("Trips table not found")
    tt = files[trips_table_path].decode("utf-8")
    if "Despatch (d)" not in tt:
        # ref was B6:V138 with 21 columns; extend to B6:X138 with +2.
        tt = re.sub(r'ref="B6:V138"', 'ref="B6:X138"', tt)
        tt = re.sub(r'(<autoFilter\s+ref=")B6:V137(")', r'\g<1>B6:X137\g<2>', tt)
        tt = re.sub(
            r'(<tableColumns[^>]*\bcount=")(\d+)(")',
            lambda mm: f'{mm.group(1)}{int(mm.group(2)) + 2}{mm.group(3)}',
            tt, count=1,
        )
        new_cols = (
            '<tableColumn id="401" name="Despatch (d)">'
            '<calculatedColumnFormula>'
            'IF(Trips[[#This Row],[Waiting (d)]]="","",'
            'MAX(0,Trips[[#This Row],[Laytime (d)]]-Trips[[#This Row],[Waiting (d)]]))'
            '</calculatedColumnFormula>'
            '</tableColumn>'
            '<tableColumn id="402" name="Despatch (USD)">'
            '<calculatedColumnFormula>'
            'IF(Trips[[#This Row],[Despatch (d)]]="",0,'
            'Trips[[#This Row],[Despatch (d)]]*IFERROR(VLOOKUP(Trips[[#This Row],[Deal No.]],Deals[#All],11,FALSE),0))'
            '</calculatedColumnFormula>'
            '</tableColumn>'
        )
        tt = tt.replace("</tableColumns>", new_cols + "</tableColumns>")
        files[trips_table_path] = tt.encode("utf-8")

        # Add header cells W6, X6 on Trips Ledger sheet
        trips_path = sheets["Trips Ledger"]
        ts = files[trips_path].decode("utf-8")
        ts = re.sub(
            r'(<c r="V6"[^>]*>.*?</c>)',
            r'\g<1><c r="W6" t="inlineStr"><is><t>Despatch (d)</t></is></c><c r="X6" t="inlineStr"><is><t>Despatch (USD)</t></is></c>',
            ts, count=1, flags=re.DOTALL,
        )
        files[trips_path] = ts.encode("utf-8")

    # ===== 3. Claims: add Issuer column ==================================
    claims_table_path = None
    for n in files:
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            if b'displayName="Claims"' in files[n]:
                claims_table_path = n
                break
    clt = files[claims_table_path].decode("utf-8")
    if "Issuer" not in clt:
        # was B6:X56, count=23.  Extend to B6:Y56, count=24.
        clt = re.sub(r'ref="B6:X56"', 'ref="B6:Y56"', clt)
        clt = re.sub(r'(<autoFilter\s+ref=")B6:X55(")', r'\g<1>B6:Y55\g<2>', clt)
        clt = re.sub(r'(<tableColumns[^>]*\bcount=")23(")', r'\g<1>24\g<2>', clt)
        new_col = '<tableColumn id="305" name="Issuer"/>'
        clt = clt.replace("</tableColumns>", new_col + "</tableColumns>")
        files[claims_table_path] = clt.encode("utf-8")

        claims_path = sheets["Claims"]
        csx = files[claims_path].decode("utf-8")
        csx = re.sub(
            r'(<c r="X6"[^>]*>.*?</c>)',
            r'\g<1><c r="Y6" t="inlineStr"><is><t>Issuer</t></is></c>',
            csx, count=1, flags=re.DOTALL,
        )
        # Extend conditional formatting range from B7:X55 to B7:Y55.
        csx = csx.replace('sqref="B7:X55"', 'sqref="B7:Y55"')
        # Add data validation for Issuer (drop-down on Entities[Code]).
        new_dv = (
            '<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="Y7:Y55">'
            '<formula1>=Entities[Code]</formula1>'
            '</dataValidation>'
        )
        m_dv = re.search(r'<dataValidations\s+count="(\d+)">', csx)
        if m_dv:
            new_count = int(m_dv.group(1)) + 1
            csx = csx.replace(
                m_dv.group(0), f'<dataValidations count="{new_count}">', 1)
            csx = csx.replace(
                '</dataValidations>', new_dv + '</dataValidations>', 1)
        # Bump dimension
        csx = re.sub(r'<dimension ref="B2:X56"', '<dimension ref="B2:Y56"', csx)
        files[claims_path] = csx.encode("utf-8")

    # ===== 4. Entities table on Company ==================================
    co_path = sheets["Company"]
    cox = files[co_path].decode("utf-8")
    if 'displayName="Entities"' not in "".join(
            files[n].decode("utf-8", "ignore")
            for n in files if n.startswith("xl/tables/")):
        # Add Entities table at B36:H38 (header + 2 entity rows) on Company.
        # Default rows: MOCOH SA + MOCZAM.
        ent_rows = (
            '<row r="35" spans="2:8"><c r="B35" t="inlineStr"><is><t>ENTITIES (multi-issuer)</t></is></c></row>'
            '<row r="36" spans="2:8">'
            '<c r="B36" t="inlineStr"><is><t>Code</t></is></c>'
            '<c r="C36" t="inlineStr"><is><t>Legal Name</t></is></c>'
            '<c r="D36" t="inlineStr"><is><t>Address</t></is></c>'
            '<c r="E36" t="inlineStr"><is><t>VAT/Reg.</t></is></c>'
            '<c r="F36" t="inlineStr"><is><t>Bank IBAN</t></is></c>'
            '<c r="G36" t="inlineStr"><is><t>Bank SWIFT</t></is></c>'
            '<c r="H36" t="inlineStr"><is><t>Notes</t></is></c>'
            '</row>'
            '<row r="37" spans="2:8">'
            '<c r="B37" t="inlineStr"><is><t>MOCOH</t></is></c>'
            '<c r="C37" t="inlineStr"><is><t>MOCOH SA</t></is></c>'
            '<c r="D37" t="inlineStr"><is><t>Rue de la Corraterie 5-7, 1204 Geneva, Switzerland</t></is></c>'
            '<c r="E37" t="inlineStr"><is><t>CHE-110.540.819</t></is></c>'
            '<c r="F37" t="inlineStr"><is><t>CH79 0853 7603 0748 0040 0</t></is></c>'
            '<c r="G37" t="inlineStr"><is><t>BICFCHGGXXX</t></is></c>'
            '<c r="H37" t="inlineStr"><is><t>Default issuer</t></is></c>'
            '</row>'
            '<row r="38" spans="2:8">'
            '<c r="B38" t="inlineStr"><is><t>MOCZAM</t></is></c>'
            '<c r="C38" t="inlineStr"><is><t>MOCZAM LTD</t></is></c>'
            '<c r="D38" t="inlineStr"><is><t>Maputo, Mozambique</t></is></c>'
            '<c r="E38" t="inlineStr"><is><t></t></is></c>'
            '<c r="F38" t="inlineStr"><is><t></t></is></c>'
            '<c r="G38" t="inlineStr"><is><t></t></is></c>'
            '<c r="H38" t="inlineStr"><is><t>Mozambique entity</t></is></c>'
            '</row>'
        )
        cox = cox.replace("</sheetData>", ent_rows + "</sheetData>", 1)
        files[co_path] = cox.encode("utf-8")

        # Create the Entities table xml.
        next_table_id = _max_table_id(files) + 1
        ent_table_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<table xmlns="{NS_MAIN}"
       id="{next_table_id}" name="Entities" displayName="Entities"
       ref="B36:H38" totalsRowShown="0">
  <autoFilter ref="B36:H38"/>
  <tableColumns count="7">
    <tableColumn id="1" name="Code"/>
    <tableColumn id="2" name="Legal Name"/>
    <tableColumn id="3" name="Address"/>
    <tableColumn id="4" name="VAT/Reg."/>
    <tableColumn id="5" name="Bank IBAN"/>
    <tableColumn id="6" name="Bank SWIFT"/>
    <tableColumn id="7" name="Notes"/>
  </tableColumns>
  <tableStyleInfo name="TableStyleLight15" showFirstColumn="0" showLastColumn="0"
                  showRowStripes="1" showColumnStripes="0"/>
</table>'''
        files[f"xl/tables/table{next_table_id}.xml"] = ent_table_xml.encode("utf-8")

        # The Company sheet needs to reference this new table via its rels.
        rels_path = "xl/worksheets/_rels/sheet9.xml.rels"
        if rels_path in files:
            rx = files[rels_path].decode("utf-8")
            # Add a new rel for the Entities table.
            existing_rids = [int(m.group(1)) for m in re.finditer(r'Id="rId(\d+)"', rx)]
            next_rid_local = (max(existing_rids) + 1) if existing_rids else 1
            new_rel = f'<Relationship Id="rId{next_rid_local}" Type="{REL_TABLE}" Target="../tables/table{next_table_id}.xml"/>'
            rx = rx.replace("</Relationships>", new_rel + "</Relationships>")
            files[rels_path] = rx.encode("utf-8")
        else:
            files[rels_path] = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rId1" Type="{REL_TABLE}" Target="../tables/table{next_table_id}.xml"/>'
                f'</Relationships>'
            ).encode("utf-8")
            # Ensure sheet9 includes <tableParts>.
        # Make sure sheet9 (Company) declares its tableParts.  It already has
        # the Consignees table, so a tablePart entry exists.  We need to add
        # a second tablePart for the Entities table.
        cox = files[co_path].decode("utf-8")
        # Find the rId of the new Entities table we just added.
        rx = files["xl/worksheets/_rels/sheet9.xml.rels"].decode("utf-8")
        # Type attr contains URL slashes, so don't use [^/].
        m = re.search(rf'<Relationship\b[^>]*Id="(rId\d+)"[^>]*Target="\.\./tables/table{next_table_id}\.xml"[^>]*/>', rx)
        if not m:
            m = re.search(rf'<Relationship\b[^>]*Target="\.\./tables/table{next_table_id}\.xml"[^>]*Id="(rId\d+)"[^>]*/>', rx)
        new_rid = m.group(1) if m else f"rId{next_rid_local}"
        if "<tableParts" in cox:
            cox = re.sub(
                r'(<tableParts[^>]*\bcount=")(\d+)(")',
                lambda mm: f'{mm.group(1)}{int(mm.group(2)) + 1}{mm.group(3)}',
                cox, count=1,
            )
            cox = cox.replace(
                "</tableParts>",
                f'<tablePart r:id="{new_rid}"/></tableParts>',
                1,
            )
        else:
            cox = cox.replace(
                "</worksheet>",
                f'<tableParts count="1"><tablePart r:id="{new_rid}"/></tableParts></worksheet>',
                1,
            )
        files[co_path] = cox.encode("utf-8")

        # Content_Types override for the new table.
        ctp = files["[Content_Types].xml"].decode("utf-8")
        ctp = ctp.replace(
            "</Types>",
            f'<Override PartName="/xl/tables/table{next_table_id}.xml" ContentType="{CT_TABLE}"/></Types>',
        )
        files["[Content_Types].xml"] = ctp.encode("utf-8")

    # ===== 5. New Statement sheet ========================================
    if "Statement" not in sheets:
        next_sheet_idx = 1 + max(
            int(re.search(r'sheet(\d+)\.xml', n).group(1))
            for n in files if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)
        )
        next_rid = _max_rid(rels) + 1
        next_sheet_id = _max_sheet_id(wb_xml) + 1

        sheet_filename = f"sheet{next_sheet_idx}.xml"
        sheet_path = f"xl/worksheets/{sheet_filename}"

        files[sheet_path] = _statement_sheet_xml().encode("utf-8")

        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="rId{next_rid}" Type="{REL_WORKSHEET}" Target="worksheets/{sheet_filename}"/></Relationships>',
        )
        new_sheet_decl = f'<sheet name="Statement" sheetId="{next_sheet_id}" r:id="rId{next_rid}"/>'
        wb_xml = wb_xml.replace("</sheets>", new_sheet_decl + "</sheets>")

        ctp = files["[Content_Types].xml"].decode("utf-8")
        ctp = ctp.replace(
            "</Types>",
            f'<Override PartName="/{sheet_path}" ContentType="{CT_WORKSHEET}"/></Types>',
        )
        files["[Content_Types].xml"] = ctp.encode("utf-8")

    # Persist workbook.xml + rels.
    files["xl/workbook.xml"] = wb_xml.encode("utf-8")
    files["xl/_rels/workbook.xml.rels"] = rels.encode("utf-8")

    # ----- write -----
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: upgrade_v6_xml.py <in.xlsm> <out.xlsm>", file=sys.stderr)
        sys.exit(2)
    upgrade(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]}")
