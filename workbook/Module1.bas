Option Explicit

' ============================================================
'  MOCOH Demurrage 2026 -- Workflow macros (auto-installed)
'  Buttons on Cover / Invoice / Claims sheets call these subs.
' ============================================================

' ---------- Generic helpers ----------------------------------

Private Function ActiveClaimRow() As ListRow
    ' Return the ListRow of the Claims table corresponding to the
    ' currently-selected cell, or Nothing if the user isn't inside
    ' the Claims table.
    On Error Resume Next
    Dim tbl As ListObject
    Set tbl = ThisWorkbook.Worksheets("Claims").ListObjects("Claims")
    If tbl Is Nothing Then Set ActiveClaimRow = Nothing: Exit Function
    Dim a As Range: Set a = ActiveCell
    If a Is Nothing Then Set ActiveClaimRow = Nothing: Exit Function
    If Intersect(a, tbl.DataBodyRange) Is Nothing Then
        Set ActiveClaimRow = Nothing
        Exit Function
    End If
    Dim rowIdx As Long
    rowIdx = a.Row - tbl.HeaderRowRange.Row
    Set ActiveClaimRow = tbl.ListRows(rowIdx)
End Function

Private Function ClaimsTbl() As ListObject
    Set ClaimsTbl = ThisWorkbook.Worksheets("Claims").ListObjects("Claims")
End Function

' ---------- Claim workflow -----------------------------------

Public Sub IssueClaim()
    Dim r As ListRow: Set r = ActiveClaimRow()
    If r Is Nothing Then
        MsgBox "Select any cell on a claim row in the Claims table first.", vbExclamation
        Exit Sub
    End If
    Dim statusCell As Range
    Set statusCell = r.Range.Cells(1, ClaimsTbl.ListColumns("Status").Index)
    Dim old As String: old = CStr(statusCell.Value)
    statusCell.Value = "Sent"
    r.Range.Cells(1, ClaimsTbl.ListColumns("Issue Date").Index).Value = Date
    Call LogAudit("Claims", statusCell.Address(False, False), "Status", old, "Sent", "Issue Claim")
End Sub

Public Sub MarkPaid()
    Dim r As ListRow: Set r = ActiveClaimRow()
    If r Is Nothing Then
        MsgBox "Select any cell on a claim row in the Claims table first.", vbExclamation
        Exit Sub
    End If
    Dim statusCell As Range
    Set statusCell = r.Range.Cells(1, ClaimsTbl.ListColumns("Status").Index)
    Dim old As String: old = CStr(statusCell.Value)
    statusCell.Value = "Paid"
    r.Range.Cells(1, ClaimsTbl.ListColumns("Paid Date").Index).Value = Date
    Call LogAudit("Claims", statusCell.Address(False, False), "Status", old, "Paid", "Mark Paid")
End Sub

Public Sub CreateClaimFromFiltered()
    Dim tb As Worksheet: Set tb = ThisWorkbook.Worksheets("Trips Ledger")
    Dim deal As Variant: deal = tb.Range("C4").Value
    If deal = "(mixed)" Or deal = "(no filter)" Or deal = "" Then
        MsgBox "Filter Trips Ledger to a single Deal No. first.", vbExclamation: Exit Sub
    End If
    Dim tbl As ListObject: Set tbl = ClaimsTbl
    Dim r As ListRow: Set r = tbl.ListRows.Add
    r.Range.Cells(1, tbl.ListColumns("Issue Date").Index).Value = Date
    r.Range.Cells(1, tbl.ListColumns("Deal No.").Index).Value = deal
    r.Range.Cells(1, tbl.ListColumns("Status").Index).Value = "Draft"
    ' Auto-generate claim no.
    r.Range.Cells(1, tbl.ListColumns("Claim No.").Index).Value = NextClaimNo()
    Call LogAudit("Claims", r.Range.Address, "(new)", "", CStr(deal) & "-DEM", "Create Claim")
    MsgBox "Draft claim created for Deal " & deal & ".", vbInformation
End Sub

' ---------- Claim number generator ---------------------------

Public Function NextClaimNo() As String
    ' Reads INV_PREFIX + INV_NEXT from the Company sheet, returns the next
    ' value AND increments the counter on Company so the next call gets a
    ' different number.  Format: <prefix><04d>, e.g. MOC-DEM-2026-0001.
    Dim ws As Worksheet: Set ws = ThisWorkbook.Worksheets("Company")
    Dim prefix As String: prefix = CStr(ws.Range("INV_PREFIX").Value)
    Dim nxt As Long: nxt = CLng(ws.Range("INV_NEXT").Value)
    NextClaimNo = prefix & Format$(nxt, "0000")
    ws.Range("INV_NEXT").Value = nxt + 1
End Function

Public Sub GenerateClaimNoForActiveRow()
    Dim r As ListRow: Set r = ActiveClaimRow()
    If r Is Nothing Then
        MsgBox "Select a claim row in the Claims table first.", vbExclamation: Exit Sub
    End If
    Dim cell As Range
    Set cell = r.Range.Cells(1, ClaimsTbl.ListColumns("Claim No.").Index)
    If Trim(CStr(cell.Value)) <> "" Then
        If MsgBox("This row already has a claim number (" & cell.Value & ")." & vbCrLf & _
                  "Overwrite?", vbYesNo + vbQuestion) <> vbYes Then Exit Sub
    End If
    cell.Value = NextClaimNo()
End Sub

' ---------- Publish PDF --------------------------------------

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

' ---------- Email ---------------------------------------------

Public Sub EmailClaim()
    Dim wsInv As Worksheet: Set wsInv = ThisWorkbook.Worksheets("Invoice")
    Dim wsCo As Worksheet:  Set wsCo  = ThisWorkbook.Worksheets("Company")
    Dim claimNo As String:  claimNo   = CStr(wsInv.Range("B20").Value)
    If Trim(claimNo) = "" Then
        MsgBox "Pick a Claim No. on Invoice!B20 first.", vbExclamation: Exit Sub
    End If

    Dim consignee As String
    consignee = CStr(wsInv.Range("F10").Value)
    Dim toAddr As String, ccAddr As String
    toAddr = LookupConsignee(consignee, "Email")
    ccAddr = LookupConsignee(consignee, "Cc Emails")
    If Left$(toAddr, 1) = "(" Then toAddr = ""

    Dim trips As ListObject
    Set trips = ThisWorkbook.Worksheets("Trips Ledger").ListObjects("Trips")
    Dim amount As Double
    amount = Application.WorksheetFunction.SumIf( _
        trips.ListColumns("Claim No.").DataBodyRange, _
        claimNo, _
        trips.ListColumns("Demurrage (USD)").DataBodyRange)
    amount = Application.WorksheetFunction.Round(amount, 2)
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

    ' Auto-export PDF for attachment.
    Dim attachPath As String
    attachPath = Environ$("TEMP") & "\Invoice_" & Replace(claimNo, "/", "-") & ".pdf"
    Application.ScreenUpdating = False
    On Error Resume Next
    ThisWorkbook.Worksheets(Array("Invoice", "Annex")).Select
    ActiveSheet.ExportAsFixedFormat Type:=xlTypePDF, _
        Filename:=attachPath, Quality:=xlQualityStandard, _
        IgnorePrintAreas:=False, OpenAfterPublish:=False
    ThisWorkbook.Worksheets("Invoice").Select
    On Error GoTo 0
    Application.ScreenUpdating = True

    On Error Resume Next
    Dim ol As Object: Set ol = CreateObject("Outlook.Application")
    If ol Is Nothing Then
        MsgBox "Outlook is not available." & vbCrLf & vbCrLf & _
               "TO:  " & toAddr & vbCrLf & _
               "CC:  " & ccAddr & vbCrLf & _
               "SUBJECT: " & subj & vbCrLf & vbCrLf & body, vbInformation
        Exit Sub
    End If
    Dim mi As Object: Set mi = ol.CreateItem(0)
    mi.To = toAddr
    mi.Cc = ccAddr
    mi.Subject = subj
    mi.Body = body
    If Dir(attachPath) <> "" Then mi.Attachments.Add attachPath
    mi.Display
    On Error GoTo 0
    Call LogEmail(claimNo, toAddr, ccAddr, subj, attachPath)
    Call LogAudit("Invoice", "B20", "Email", "", claimNo, "Open Outlook draft")
End Sub

' ---------- Bulk reminder emails -----------------------------

Public Sub SendReminders()
    ' Walk Claims, find Status="Sent" AND DaysOverdue > 0, group by
    ' consignee, and open one Outlook draft per consignee with a table
    ' of the outstanding claims.  Each draft is DISPLAYED for review,
    ' not auto-sent.
    Dim tbl As ListObject: Set tbl = ClaimsTbl
    If tbl.ListRows.Count = 0 Then
        MsgBox "No claims to remind on.", vbInformation: Exit Sub
    End If
    ' Build a dictionary: consignee -> list of (claim_no, due, amount).
    Dim dict As Object: Set dict = CreateObject("Scripting.Dictionary")
    Dim r As ListRow
    For Each r In tbl.ListRows
        Dim st As String: st = CStr(r.Range.Cells(1, tbl.ListColumns("Status").Index).Value)
        If st <> "Sent" And st <> "Partial" Then GoTo nextRow
        Dim ov As Variant: ov = r.Range.Cells(1, tbl.ListColumns("Days Overdue").Index).Value
        If Not IsNumeric(ov) Then GoTo nextRow
        If CLng(ov) <= 0 Then GoTo nextRow
        Dim cn As String: cn = CStr(r.Range.Cells(1, tbl.ListColumns("Consignee").Index).Value)
        If cn = "" Then GoTo nextRow
        If Not dict.Exists(cn) Then dict.Add cn, ""
        Dim line As String
        line = CStr(r.Range.Cells(1, tbl.ListColumns("Claim No.").Index).Value) & vbTab & _
               "Due: " & Format$(r.Range.Cells(1, tbl.ListColumns("Due Date").Index).Value, "dd-mmm-yyyy") & vbTab & _
               "USD " & Format$(r.Range.Cells(1, tbl.ListColumns("Amount (USD)").Index).Value, "#,##0.00") & vbTab & _
               CLng(ov) & " days overdue"
        dict(cn) = dict(cn) & line & vbCrLf
nextRow:
    Next r
    If dict.Count = 0 Then
        MsgBox "No overdue claims to remind on.", vbInformation: Exit Sub
    End If
    Dim companyName As String: companyName = CStr(ThisWorkbook.Worksheets("Company").Range("COMPANY_NAME").Value)
    Dim ol As Object: Set ol = CreateObject("Outlook.Application")
    If ol Is Nothing Then
        MsgBox "Outlook is not available.", vbExclamation: Exit Sub
    End If
    Dim k As Variant, drafts As Long
    For Each k In dict.Keys
        Dim toAddr As String, ccAddr As String
        toAddr = LookupConsignee(CStr(k), "Email")
        ccAddr = LookupConsignee(CStr(k), "Cc Emails")
        If Left$(toAddr, 1) = "(" Then toAddr = ""
        Dim body As String
        body = "Dear all," & vbCrLf & vbCrLf & _
               "Friendly reminder on the following outstanding demurrage invoices:" & vbCrLf & vbCrLf & _
               dict(k) & vbCrLf & _
               "Please confirm payment status / expected settlement date." & vbCrLf & vbCrLf & _
               "Thank you very much." & vbCrLf & vbCrLf & _
               "Kind regards," & vbCrLf & companyName
        Dim mi As Object: Set mi = ol.CreateItem(0)
        mi.To = toAddr
        mi.Cc = ccAddr
        mi.Subject = "Demurrage invoices - payment reminder"
        mi.Body = body
        mi.Display
        Call LogEmail("(multi)", toAddr, ccAddr, mi.Subject, "")
        drafts = drafts + 1
    Next k
    MsgBox drafts & " reminder draft(s) opened in Outlook for review.", vbInformation
End Sub

' ---------- Lookups & logging --------------------------------

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

Public Sub LogEmail(claimNo As String, toAddr As String, ccAddr As String, _
                    subj As String, attachPath As String)
    On Error Resume Next
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets("EmailLog")
    If ws Is Nothing Then Exit Sub
    Dim tbl As ListObject: Set tbl = ws.ListObjects("EmailLog")
    If tbl Is Nothing Then Exit Sub
    Dim r As ListRow: Set r = tbl.ListRows.Add
    r.Range.Cells(1, 1).Value = Now
    r.Range.Cells(1, 2).Value = Environ$("USERNAME")
    r.Range.Cells(1, 3).Value = claimNo
    r.Range.Cells(1, 4).Value = toAddr
    r.Range.Cells(1, 5).Value = ccAddr
    r.Range.Cells(1, 6).Value = subj
    r.Range.Cells(1, 7).Value = attachPath
End Sub
