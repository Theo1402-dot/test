"""Upgrade the MOCOH demurrage workbook:

  1. Extend Consignees table with a 'Cc Emails' column (for rubis/lake/etc).
  2. Wire the Invoice 'open email' link to a real mailto: that includes
     the To address, the Cc list, the subject, AND the URL-encoded body
     (so no copy-paste is needed any more).
  3. Replace the broken 'Publish PDF' macro button on Invoice with clear
     instructions for the no-macro print path (Print Areas already set).
  4. Set Print Areas + landscape + fit-to-page on Invoice and Annex so
     Ctrl+P -> Save as PDF produces a clean two-page document.
  5. Rewrite the Macros sheet with corrected, ready-to-paste VBA:
       - EmailClaim (opens Outlook with To/Cc/Subject/Body filled)
       - PublishInvoicePDF (handles empty claim no, no Adobe dependency)
       - IssueClaim / MarkPaid / CreateClaimFromFiltered / LogAudit (kept)
  6. Keep all existing VBA project bytes intact (don't break the .xlsm).

Usage:  python3 scripts/upgrade_demurrage_xlsm.py <in.xlsm> <out.xlsm>
"""

from __future__ import annotations
import sys
from copy import copy
import openpyxl
from openpyxl.worksheet.table import TableColumn
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.page import PageMargins, PrintOptions


# ----- VBA source code (paste-into-Module1 ready) -----

VBA_MODULE1 = '''Option Explicit

' ============================================================
'  MOCOH Demurrage 2026 -- Workflow macros
'  Paste this entire module into a NEW Module (Alt+F11 -> Insert -> Module).
'  Then assign macros to the matching buttons on the sheets.
' ============================================================

Public Sub IssueClaim()
    Dim ws As Worksheet: Set ws = ThisWorkbook.Worksheets("Claims")
    Dim r As Long: r = ActiveCell.Row
    If ActiveSheet.Name <> "Claims" Or r < 7 Or r > 15 Then
        MsgBox "Select a claim row (7-15) on the Claims sheet first.", vbExclamation: Exit Sub
    End If
    Dim old As String: old = CStr(ws.Cells(r, "L").Value)
    ws.Cells(r, "L").Value = "Sent"
    ws.Cells(r, "C").Value = Date
    Call LogAudit("Claims", "L" & r, "Status", old, "Sent", "Issue Claim")
End Sub

Public Sub MarkPaid()
    Dim ws As Worksheet: Set ws = ThisWorkbook.Worksheets("Claims")
    Dim r As Long: r = ActiveCell.Row
    If ActiveSheet.Name <> "Claims" Or r < 7 Or r > 15 Then
        MsgBox "Select a claim row (7-15) on the Claims sheet first.", vbExclamation: Exit Sub
    End If
    Dim old As String: old = CStr(ws.Cells(r, "L").Value)
    ws.Cells(r, "L").Value = "Paid"
    ws.Cells(r, "N").Value = Date
    Call LogAudit("Claims", "L" & r, "Status", old, "Paid", "Mark Paid")
End Sub

Public Sub CreateClaimFromFiltered()
    Dim tb As Worksheet: Set tb = ThisWorkbook.Worksheets("Trips Ledger")
    Dim deal As Variant: deal = tb.Range("C4").Value
    If deal = "(mixed)" Or deal = "(no filter)" Or deal = "" Then
        MsgBox "Filter Trips Ledger to a single Deal No. first.", vbExclamation: Exit Sub
    End If
    Dim tbl As ListObject: Set tbl = ThisWorkbook.Worksheets("Claims").ListObjects("Claims")
    Dim r As ListRow: Set r = tbl.ListRows.Add
    r.Range.Cells(1, 2).Value = Date
    r.Range.Cells(1, 3).Value = deal
    r.Range.Cells(1, 10).Value = "Draft"
    Call LogAudit("Claims", r.Range.Address, "(new)", "", deal & "-DEM", "Create Claim")
    MsgBox "Draft claim created for Deal " & deal & ".", vbInformation
End Sub

' ------------------------------------------------------------
'  PublishInvoicePDF
'    Exports Invoice + Annex tabs to a single PDF.
'    Fixes vs. the old version:
'      - validates that a claim number is selected on Invoice!B20
'      - OpenAfterPublish:=False (no dependency on Adobe Reader)
'      - reselects the Invoice tab cleanly afterwards
' ------------------------------------------------------------
Public Sub PublishInvoicePDF()
    Dim claimNo As String
    claimNo = CStr(ThisWorkbook.Worksheets("Invoice").Range("B20").Value)
    If Trim(claimNo) = "" Then
        MsgBox "Pick a Claim No. on Invoice!B20 first.", vbExclamation: Exit Sub
    End If
    Dim defaultName As String
    defaultName = "Invoice_" & Replace(claimNo, "/", "-") & ".pdf"
    Dim savePath As Variant
    savePath = Application.GetSaveAsFilename( _
        InitialFileName:=defaultName, _
        FileFilter:="PDF Files (*.pdf), *.pdf")
    If savePath = False Then Exit Sub

    Application.ScreenUpdating = False
    On Error GoTo cleanup
    ThisWorkbook.Worksheets(Array("Invoice", "Annex")).Select
    ActiveSheet.ExportAsFixedFormat Type:=xlTypePDF, _
        Filename:=CStr(savePath), Quality:=xlQualityStandard, _
        IgnorePrintAreas:=False, OpenAfterPublish:=False
cleanup:
    ThisWorkbook.Worksheets("Invoice").Select
    Application.ScreenUpdating = True
    If Err.Number = 0 Then
        Call LogAudit("Invoice", "B20", "PDF", "", claimNo, "Publish PDF")
        MsgBox "PDF saved to:" & vbCrLf & savePath, vbInformation
    Else
        MsgBox "PDF export failed: " & Err.Description, vbExclamation
    End If
End Sub

' ------------------------------------------------------------
'  EmailClaim
'    Opens Outlook with To / Cc / Subject / Body pre-filled
'    AND attaches the freshly-exported Invoice PDF.
'    The mail is DISPLAYED (not sent) so you can review first.
'    Recipients:
'      To  = Consignees[Email]      (looked up from Claims[Consignee])
'      Cc  = Consignees[Cc Emails]  (free-text list, semicolon or comma)
' ------------------------------------------------------------
Public Sub EmailClaim()
    Dim wsInv As Worksheet: Set wsInv = ThisWorkbook.Worksheets("Invoice")
    Dim wsCo As Worksheet:  Set wsCo  = ThisWorkbook.Worksheets("Company")
    Dim claimNo As String:  claimNo   = CStr(wsInv.Range("B20").Value)
    If Trim(claimNo) = "" Then
        MsgBox "Pick a Claim No. on Invoice!B20 first.", vbExclamation: Exit Sub
    End If

    ' Resolve the To/Cc by walking the Consignees table.
    Dim consignee As String, billTo As String
    consignee = CStr(wsInv.Range("F10").Value)   ' formula already resolves it
    Dim toAddr As String, ccAddr As String
    toAddr = LookupConsignee(consignee, "Email")
    ccAddr = LookupConsignee(consignee, "Cc Emails")
    If Left$(toAddr, 1) = "(" Then toAddr = ""   ' "(awaiting email)" -> blank

    ' Numbers shown to the user.
    Dim amount As Double
    amount = Application.WorksheetFunction.Round( _
        Application.WorksheetFunction.SumIf( _
            ThisWorkbook.Worksheets("Trips Ledger").ListObjects("Trips").ListColumns("Claim No.").DataBodyRange, _
            claimNo, _
            ThisWorkbook.Worksheets("Trips Ledger").ListObjects("Trips").ListColumns("Demurrage (USD)").DataBodyRange), 2)
    Dim dealNo As String: dealNo = CStr(wsInv.Range("F17").Value)
    Dim companyName As String: companyName = CStr(wsCo.Range("C7").Value)

    Dim subj As String
    subj = "Demurrage Invoice " & claimNo & " - Deal " & dealNo

    Dim body As String
    body = "Dear all," & vbCrLf & vbCrLf & _
           "Please find attached our demurrage invoice for deal " & dealNo & _
           " for USD " & Format$(amount, "#,##0.00") & "." & vbCrLf & vbCrLf & _
           "Kindly confirm receipt and share the swift once available." & vbCrLf & vbCrLf & _
           "Thank you very much." & vbCrLf & vbCrLf & _
           "Kind regards," & vbCrLf & companyName

    ' Optionally export the PDF first so we can attach it.
    Dim attachPath As String: attachPath = ""
    If MsgBox("Attach PDF of Invoice + Annex to the email?", vbYesNo + vbQuestion, _
              "Attach PDF?") = vbYes Then
        attachPath = Environ$("TEMP") & "\Invoice_" & Replace(claimNo, "/", "-") & ".pdf"
        Application.ScreenUpdating = False
        ThisWorkbook.Worksheets(Array("Invoice", "Annex")).Select
        ActiveSheet.ExportAsFixedFormat Type:=xlTypePDF, _
            Filename:=attachPath, Quality:=xlQualityStandard, _
            IgnorePrintAreas:=False, OpenAfterPublish:=False
        ThisWorkbook.Worksheets("Invoice").Select
        Application.ScreenUpdating = True
    End If

    ' Open the Outlook draft.
    On Error Resume Next
    Dim ol As Object: Set ol = CreateObject("Outlook.Application")
    If ol Is Nothing Then
        MsgBox "Outlook is not available. The body and recipients are shown below" & _
               vbCrLf & vbCrLf & "TO:  " & toAddr & vbCrLf & "CC:  " & ccAddr & _
               vbCrLf & "SUBJECT: " & subj & vbCrLf & vbCrLf & body, vbInformation
        Exit Sub
    End If
    Dim mi As Object: Set mi = ol.CreateItem(0)   ' 0 = olMailItem
    mi.To = toAddr
    mi.Cc = ccAddr
    mi.Subject = subj
    mi.Body = body
    If attachPath <> "" Then mi.Attachments.Add attachPath
    mi.Display      ' SHOW the draft -- do not auto-Send
    On Error GoTo 0
    Call LogAudit("Invoice", "B20", "Email", "", claimNo, "Open Outlook draft")
End Sub

' Lookup helper for the Consignees table on Company.
Private Function LookupConsignee(ByVal name As String, ByVal col As String) As String
    On Error Resume Next
    Dim tbl As ListObject
    Set tbl = ThisWorkbook.Worksheets("Company").ListObjects("Consignees")
    Dim v As Variant
    v = Application.WorksheetFunction.VLookup( _
        name, tbl.Range, _
        Application.WorksheetFunction.Match(col, tbl.HeaderRowRange, 0), False)
    If IsError(v) Then
        LookupConsignee = ""
    Else
        LookupConsignee = CStr(v)
    End If
End Function

Public Sub LogAudit(sht As String, addr As String, fld As String, _
                    oldV As String, newV As String, act As String)
    On Error Resume Next
    Dim tbl As ListObject
    Set tbl = ThisWorkbook.Worksheets("AuditLog").ListObjects("AuditLog")
    Dim r As ListRow: Set r = tbl.ListRows.Add
    r.Range.Cells(1, 1).Value = Now
    r.Range.Cells(1, 2).Value = Environ$("USERNAME")
    r.Range.Cells(1, 3).Value = sht
    r.Range.Cells(1, 4).Value = addr
    r.Range.Cells(1, 5).Value = fld
    r.Range.Cells(1, 6).Value = oldV
    r.Range.Cells(1, 7).Value = newV
    r.Range.Cells(1, 8).Value = act
End Sub
'''

VBA_THISWORKBOOK = '''Option Explicit

' Paste into the ThisWorkbook object (NOT a module).

Private Sub Workbook_SheetChange(ByVal Sh As Object, ByVal Target As Range)
    If Sh.Name <> "Claims" Or Target.Cells.Count <> 1 Then Exit Sub
    If Target.Column <> 12 Or Target.Row < 7 Or Target.Row > 15 Then Exit Sub
    Application.EnableEvents = False
    Call LogAudit("Claims", Target.Address(False, False), "Status", _
                  "(prev)", CStr(Target.Value), "Manual edit")
    Application.EnableEvents = True
End Sub
'''


# ----- Mailto formula builder (URL-encoded body + cc, all in pure Excel) -----

def build_mailto_formula() -> str:
    """Return an Excel formula that evaluates to a HYPERLINK to a fully
    populated mailto: link (To, Cc, Subject, Body).  The body is
    URL-encoded inline using nested SUBSTITUTE() over the few characters
    Outlook actually cares about for mailto: links."""
    # Inputs we resolve via VLOOKUPs against existing tables.
    consignee = "IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],4,FALSE),\"\")"
    to_raw = f"IFERROR(VLOOKUP({consignee},Consignees[],3,FALSE),\"\")"
    cc_raw = f"IFERROR(VLOOKUP({consignee},Consignees[],4,FALSE),\"\")"
    deal_no = "IFERROR(VLOOKUP(INV_CLAIM,Claims[#All],3,FALSE),\"\")"
    amount = ("TEXT(ROUND(SUMIF(Trips[Claim No.],INV_CLAIM,Trips[Demurrage (USD)])"
              "*(1+VAT_RATE),2),\"#,##0.00\")")

    # Drop "(awaiting email)" placeholders so they don't end up in the To/Cc.
    to_clean = f'IF(LEFT({to_raw},1)="(","",{to_raw})'
    cc_clean = f'IF(LEFT({cc_raw},1)="(","",{cc_raw})'

    subject = '"Demurrage Invoice "&INV_CLAIM&" - Deal "&' + deal_no

    body_plain = (
        '"Dear all,"&CHAR(10)&CHAR(10)'
        '&"Please find attached our demurrage invoice for deal "&' + deal_no +
        '&" for USD "&' + amount + '&"."&CHAR(10)&CHAR(10)'
        '&"Kindly confirm receipt and share the swift once available."'
        '&CHAR(10)&CHAR(10)&"Thank you very much."'
        '&CHAR(10)&CHAR(10)&"Kind regards,"&CHAR(10)&COMPANY_NAME'
    )

    # URL-encode the body for the mailto link.  We only need to escape
    # the handful of characters Outlook gets wrong inside a mailto.
    def enc(field: str) -> str:
        return (
            f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE('
            f'{field},"&","%26"),CHAR(10),"%0A"),"  "," "),"""","%22")'
        )
    body_enc = enc(body_plain)
    subj_enc = f'SUBSTITUTE({subject},"&","%26")'

    link = (
        '"mailto:"&' + to_clean +
        '&"?cc="&' + cc_clean +
        '&"&subject="&' + subj_enc +
        '&"&body="&' + body_enc
    )
    return f'=HYPERLINK({link}, "Open email draft (To + Cc + body all pre-filled)")'


# ----- Main upgrade flow -----

def upgrade(src: str, dst: str) -> None:
    wb = openpyxl.load_workbook(src, keep_vba=True)

    # 1) Consignees table: add 'Cc Emails' column.
    company = wb["Company"]
    consignees = company.tables["Consignees"]
    have_cc = any(c.name == "Cc Emails" for c in consignees.tableColumns)
    if not have_cc:
        # Move table reference one column wider: B30:D33 -> B30:E33.
        consignees.ref = "B30:E33"
        if consignees.autoFilter is not None:
            consignees.autoFilter.ref = "B30:E33"
        next_id = max(c.id for c in consignees.tableColumns) + 1
        consignees.tableColumns.append(TableColumn(id=next_id, name="Cc Emails"))
        # Header cell + light styling to match.
        hdr = company["E30"]
        hdr.value = "Cc Emails"
        hdr.font = copy(company["D30"].font)
        hdr.fill = copy(company["D30"].fill)
        hdr.alignment = copy(company["D30"].alignment)
        hdr.border = copy(company["D30"].border)
        # Leave Cc cells empty; user fills them in.  Column width to fit.
        company.column_dimensions["E"].width = 52
        # Hint cell ABOVE the table.
        hint = company["B28"]
        if not hint.value:
            hint.value = (
                "Tip: put extra recipients (e.g. transporter ops, internal AR) in "
                "the new Cc Emails column, comma- or semicolon-separated. They will "
                "be added to every claim email for that consignee."
            )
            hint.font = Font(italic=True, color="6B7280", size=10)
            hint.alignment = Alignment(wrap_text=True)

    # Clarify the placeholder emails so the user can spot what to fill.
    company["D31"].value = "(awaiting Rubis Energy email)"
    company["D32"].value = "(awaiting Lake Petroleum email)"

    # 2) Invoice mailto with To + Cc + Body, plus replace the broken
    #    PDF button with clear no-macro print instructions.
    inv = wb["Invoice"]
    inv["B36"].value = build_mailto_formula()
    inv["B38"].value = "Email body preview (for reference; the link above pre-fills it):"
    # B39 already has a working body formula; keep it.

    # The old "📄 Publish PDF (assign macro: PublishInvoicePDF)" button is
    # broken unless the user installs the VBA.  Replace with a working flow.
    inv["E36"].value = (
        "PDF: hold Ctrl, click both the Invoice and Annex tabs, then "
        "Ctrl+P -> Microsoft Print to PDF -> Save.  "
        "(After installing the VBA, the EmailClaim macro can do this in one click.)"
    )
    inv["E36"].font = Font(bold=True, color="1F4E79")
    inv["E36"].alignment = Alignment(wrap_text=True, vertical="center")

    # 3) Print areas + page setup for Invoice and Annex.
    for name, area in (("Invoice", "B1:I50"), ("Annex", "B1:K62")):
        ws = wb[name]
        ws.print_area = area
        ws.page_setup.orientation = ws.ORIENTATION_PORTRAIT
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.6, bottom=0.6,
                                      header=0.3, footer=0.3)
        ws.print_options = PrintOptions(horizontalCentered=True)

    # 4) Rewrite Macros sheet -- clearer instructions + corrected source.
    mac = wb["Macros"]
    # Clear rows 1..40
    for r in range(1, 41):
        for c in range(1, 6):
            mac.cell(row=r, column=c).value = None
    mac["B1"].value = "<- Back to Cover"
    mac["B1"].hyperlink = "#'Cover'!A1"
    mac["B1"].font = Font(color="1F4E79", underline="single")

    mac["B2"].value = "ONE-TIME VBA SETUP"
    mac["B2"].font = Font(bold=True, size=14)
    mac["B3"].value = (
        "1. Press Alt+F11 to open the VBA editor.\n"
        "2. In the Project tree on the left, find this workbook -> Modules. "
        "If 'Module1' doesn't exist, right-click the project -> Insert -> Module.\n"
        "3. Double-click Module1, delete anything inside, and paste the "
        "WORKFLOW MODULE code from row 6 below.\n"
        "4. Double-click 'ThisWorkbook' (under 'Microsoft Excel Objects'), "
        "delete anything inside, and paste the THISWORKBOOK code from row 8 below.\n"
        "5. File -> Save (Ctrl+S).  The Print PDF + Email buttons now work.\n\n"
        "Without this setup, you can still:\n"
        "  - Use the Invoice 'Open email draft' link (purely formula-based, "
        "no VBA needed) to send claims.\n"
        "  - Print to PDF by selecting Invoice + Annex tabs (Ctrl+click) and "
        "pressing Ctrl+P -> Microsoft Print to PDF."
    )
    mac["B3"].alignment = Alignment(wrap_text=True, vertical="top")
    mac.row_dimensions[3].height = 180

    mac["B5"].value = "WORKFLOW MODULE  --  paste into Module1"
    mac["B5"].font = Font(bold=True, size=12, color="1F4E79")
    mac["B6"].value = VBA_MODULE1
    mac["B6"].alignment = Alignment(wrap_text=True, vertical="top")
    mac.row_dimensions[6].height = 600

    mac["B7"].value = "THISWORKBOOK  --  paste into the ThisWorkbook object"
    mac["B7"].font = Font(bold=True, size=12, color="1F4E79")
    mac["B8"].value = VBA_THISWORKBOOK
    mac["B8"].alignment = Alignment(wrap_text=True, vertical="top")
    mac.row_dimensions[8].height = 140

    mac.column_dimensions["B"].width = 120

    # Save.
    wb.save(dst)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: upgrade_demurrage_xlsm.py <in.xlsm> <out.xlsm>", file=sys.stderr)
        sys.exit(2)
    upgrade(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]}")
