Option Explicit

' ============================================================
'  MOCOH Demurrage 2026 -- Workflow macros (auto-installed)
' ============================================================

' ---------- Generic helpers ----------------------------------

Private Function ActiveClaimRow() As ListRow
    On Error Resume Next
    Dim tbl As ListObject
    Set tbl = ThisWorkbook.Worksheets("Claims").ListObjects("Claims")
    If tbl Is Nothing Then Set ActiveClaimRow = Nothing: Exit Function
    Dim a As Range: Set a = ActiveCell
    If a Is Nothing Then Set ActiveClaimRow = Nothing: Exit Function
    If Intersect(a, tbl.DataBodyRange) Is Nothing Then
        Set ActiveClaimRow = Nothing: Exit Function
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
        MsgBox "Select any cell on a claim row in the Claims table first.", vbExclamation: Exit Sub
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
        MsgBox "Select any cell on a claim row in the Claims table first.", vbExclamation: Exit Sub
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
    r.Range.Cells(1, tbl.ListColumns("Claim No.").Index).Value = NextClaimNo()
    Call LogAudit("Claims", r.Range.Address, "(new)", "", CStr(deal) & "-DEM", "Create Claim")
    MsgBox "Draft claim created for Deal " & deal & ".", vbInformation
End Sub

' ---------- Claim number generator ---------------------------

Public Function NextClaimNo() As String
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
               "TO:  " & toAddr & vbCrLf & "CC:  " & ccAddr & vbCrLf & _
               "SUBJECT: " & subj & vbCrLf & vbCrLf & body, vbInformation
        Exit Sub
    End If
    Dim mi As Object: Set mi = ol.CreateItem(0)
    mi.To = toAddr: mi.Cc = ccAddr
    mi.Subject = subj: mi.Body = body
    If Dir(attachPath) <> "" Then mi.Attachments.Add attachPath
    mi.Display
    On Error GoTo 0
    Call LogEmail(claimNo, toAddr, ccAddr, subj, attachPath)
    Call LogAudit("Invoice", "B20", "Email", "", claimNo, "Open Outlook draft")
End Sub

Public Sub SendReminders()
    Dim tbl As ListObject: Set tbl = ClaimsTbl
    If tbl.ListRows.Count = 0 Then
        MsgBox "No claims to remind on.", vbInformation: Exit Sub
    End If
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
        mi.To = toAddr: mi.Cc = ccAddr
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

' ============================================================
'  Statement of Account                       (Tier 3)
' ============================================================

Public Sub GenerateStatement()
    Dim wsS As Worksheet
    On Error Resume Next
    Set wsS = ThisWorkbook.Worksheets("Statement")
    On Error GoTo 0
    If wsS Is Nothing Then
        MsgBox "Statement sheet not found.", vbExclamation: Exit Sub
    End If

    Dim consignee As String: consignee = CStr(wsS.Range("C3").Value)
    If consignee = "" Then
        MsgBox "Pick a consignee from the drop-down on Statement!C3 first.", vbExclamation: Exit Sub
    End If

    Application.ScreenUpdating = False
    ' Clear any previous content from row 8 down.
    wsS.Range("B8:K200").ClearContents

    Dim co As Worksheet: Set co = ThisWorkbook.Worksheets("Company")
    Dim companyName As String: companyName = CStr(co.Range("COMPANY_NAME").Value)
    Dim today As Date: today = Date

    ' Pull consignee row from Consignees table for header info.
    Dim addr As String: addr = LookupConsignee(consignee, "Bill-To Address")
    Dim email As String: email = LookupConsignee(consignee, "Email")
    Dim credit As Double: credit = Val(LookupConsignee(consignee, "Credit Limit (USD)"))

    ' Header
    wsS.Range("B5").Value = "Statement issued by"
    wsS.Range("C5").Value = companyName
    wsS.Range("F5").Value = "Statement date"
    wsS.Range("G5").Value = today
    wsS.Range("B6").Value = "Account:"
    wsS.Range("C6").Value = consignee
    wsS.Range("F6").Value = "Credit limit"
    wsS.Range("G6").Value = credit

    Dim row As Long: row = 8
    wsS.Cells(row, 2).Value = "OPEN CLAIMS"
    wsS.Cells(row, 2).Font.Bold = True
    row = row + 1
    wsS.Cells(row, 2).Value = "Claim No."
    wsS.Cells(row, 3).Value = "Deal"
    wsS.Cells(row, 4).Value = "Issue Date"
    wsS.Cells(row, 5).Value = "Due Date"
    wsS.Cells(row, 6).Value = "Amount"
    wsS.Cells(row, 7).Value = "Paid"
    wsS.Cells(row, 8).Value = "Outstanding"
    wsS.Cells(row, 9).Value = "Status"
    wsS.Cells(row, 10).Value = "Aging"
    Dim hdrRange As Range: Set hdrRange = wsS.Range("B" & row & ":J" & row)
    hdrRange.Font.Bold = True
    hdrRange.Interior.Color = RGB(31, 78, 121)
    hdrRange.Font.Color = RGB(255, 255, 255)
    row = row + 1
    Dim startData As Long: startData = row

    Dim tbl As ListObject: Set tbl = ClaimsTbl
    Dim totAmt As Double, totPaid As Double, totOut As Double
    Dim r As ListRow
    For Each r In tbl.ListRows
        Dim cn As String
        cn = CStr(r.Range.Cells(1, tbl.ListColumns("Consignee").Index).Value)
        If cn <> consignee Then GoTo nextC
        Dim st As String
        st = CStr(r.Range.Cells(1, tbl.ListColumns("Status").Index).Value)
        If st = "Cancelled" Then GoTo nextC
        wsS.Cells(row, 2).Value = r.Range.Cells(1, tbl.ListColumns("Claim No.").Index).Value
        wsS.Cells(row, 3).Value = r.Range.Cells(1, tbl.ListColumns("Deal No.").Index).Value
        wsS.Cells(row, 4).Value = r.Range.Cells(1, tbl.ListColumns("Issue Date").Index).Value
        wsS.Cells(row, 5).Value = r.Range.Cells(1, tbl.ListColumns("Due Date").Index).Value
        Dim amt As Double, pd As Double, outv As Double
        amt = Val(CStr(r.Range.Cells(1, tbl.ListColumns("Amount (USD)").Index).Value))
        pd  = Val(CStr(r.Range.Cells(1, tbl.ListColumns("Paid (USD)").Index).Value))
        outv = amt - pd
        wsS.Cells(row, 6).Value = amt
        wsS.Cells(row, 7).Value = pd
        wsS.Cells(row, 8).Value = outv
        wsS.Cells(row, 9).Value = st
        wsS.Cells(row, 10).Value = r.Range.Cells(1, tbl.ListColumns("Aging").Index).Value
        totAmt = totAmt + amt: totPaid = totPaid + pd: totOut = totOut + outv
        row = row + 1
nextC:
    Next r
    If row = startData Then
        wsS.Cells(row, 2).Value = "(no claims for this consignee)"
        row = row + 1
    Else
        ' Totals row
        wsS.Cells(row, 2).Value = "TOTAL"
        wsS.Cells(row, 6).Value = totAmt
        wsS.Cells(row, 7).Value = totPaid
        wsS.Cells(row, 8).Value = totOut
        wsS.Range("B" & row & ":J" & row).Font.Bold = True
        wsS.Range("B" & row & ":J" & row).Borders(xlEdgeTop).LineStyle = xlContinuous
        row = row + 1
    End If
    row = row + 1
    wsS.Cells(row, 2).Value = "PAYMENTS"
    wsS.Cells(row, 2).Font.Bold = True
    row = row + 1
    wsS.Cells(row, 2).Value = "Date"
    wsS.Cells(row, 3).Value = "SWIFT Ref"
    wsS.Cells(row, 4).Value = "Claim"
    wsS.Cells(row, 5).Value = "Amount"
    wsS.Cells(row, 6).Value = "Currency"
    wsS.Cells(row, 7).Value = "Notes"
    Set hdrRange = wsS.Range("B" & row & ":G" & row)
    hdrRange.Font.Bold = True
    hdrRange.Interior.Color = RGB(31, 78, 121)
    hdrRange.Font.Color = RGB(255, 255, 255)
    row = row + 1

    Dim wsP As Worksheet: Set wsP = ThisWorkbook.Worksheets("Payments")
    Dim ptbl As ListObject: Set ptbl = wsP.ListObjects("Payments")
    Dim pcount As Long: pcount = 0
    If Not ptbl.DataBodyRange Is Nothing Then
        Dim pr As ListRow
        For Each pr In ptbl.ListRows
            If CStr(pr.Range.Cells(1, ptbl.ListColumns("Consignee").Index).Value) <> consignee Then GoTo nextP
            wsS.Cells(row, 2).Value = pr.Range.Cells(1, ptbl.ListColumns("Payment Date").Index).Value
            wsS.Cells(row, 3).Value = pr.Range.Cells(1, ptbl.ListColumns("SWIFT Ref").Index).Value
            wsS.Cells(row, 4).Value = pr.Range.Cells(1, ptbl.ListColumns("Claim No.").Index).Value
            wsS.Cells(row, 5).Value = pr.Range.Cells(1, ptbl.ListColumns("Amount").Index).Value
            wsS.Cells(row, 6).Value = pr.Range.Cells(1, ptbl.ListColumns("Currency").Index).Value
            wsS.Cells(row, 7).Value = pr.Range.Cells(1, ptbl.ListColumns("Notes").Index).Value
            pcount = pcount + 1
            row = row + 1
nextP:
        Next pr
    End If
    If pcount = 0 Then
        wsS.Cells(row, 2).Value = "(no payments received)"
        row = row + 1
    End If

    ' Format money columns.
    wsS.Range("F10:H" & (row + 1)).NumberFormat = "#,##0.00"
    wsS.Range("E10:E" & (row + 1)).NumberFormat = "#,##0.00"
    wsS.Range("D10:D" & (row + 1)).NumberFormat = "yyyy-mm-dd"
    wsS.Range("E10:E" & (row + 1)).NumberFormat = "#,##0.00"
    wsS.Columns("B:J").AutoFit

    Application.ScreenUpdating = True
    Call LogAudit("Statement", "C3", "Consignee", "", consignee, "Generate Statement")
    MsgBox "Statement generated for " & consignee & ".", vbInformation
End Sub

' ============================================================
'  Bulk CSV import for Trips                  (Tier 3)
' ============================================================

Public Sub ImportTripsFromCSV()
    Dim path As Variant
    path = Application.GetOpenFilename("CSV files (*.csv),*.csv", , _
                                       "Pick a trips CSV (header row required)")
    If path = False Then Exit Sub

    Dim fnum As Integer: fnum = FreeFile
    Dim hdr As String, line As String
    Open path For Input As #fnum
    If EOF(fnum) Then Close #fnum: MsgBox "Empty file.", vbExclamation: Exit Sub
    Line Input #fnum, hdr

    ' Parse header columns
    Dim hdrCols() As String
    hdrCols = SplitCSVLine(hdr)
    Dim tbl As ListObject
    Set tbl = ThisWorkbook.Worksheets("Trips Ledger").ListObjects("Trips")

    ' Build a map: csv-col-index -> table-col-index
    Dim mapToTbl() As Long
    ReDim mapToTbl(UBound(hdrCols))
    Dim i As Long
    For i = 0 To UBound(hdrCols)
        Dim tcol As Long
        tcol = 0
        On Error Resume Next
        tcol = tbl.ListColumns(Trim(hdrCols(i))).Index
        On Error GoTo 0
        mapToTbl(i) = tcol     ' 0 means "no matching column -- skip"
    Next i

    Dim imported As Long
    Do While Not EOF(fnum)
        Line Input #fnum, line
        If Trim(line) = "" Then GoTo nextLine
        Dim vals() As String
        vals = SplitCSVLine(line)
        Dim newRow As ListRow: Set newRow = tbl.ListRows.Add
        For i = 0 To UBound(vals)
            If i > UBound(mapToTbl) Then Exit For
            If mapToTbl(i) > 0 Then
                ' Try to coerce dates / numbers automatically.
                Dim v As String: v = vals(i)
                If IsNumeric(v) Then
                    newRow.Range.Cells(1, mapToTbl(i)).Value = CDbl(v)
                ElseIf IsDate(v) Then
                    newRow.Range.Cells(1, mapToTbl(i)).Value = CDate(v)
                Else
                    newRow.Range.Cells(1, mapToTbl(i)).Value = v
                End If
            End If
        Next i
        imported = imported + 1
nextLine:
    Loop
    Close #fnum
    Call LogAudit("Trips Ledger", "(import)", "rows", "", CStr(imported), "Import CSV " & path)
    MsgBox imported & " trip row(s) imported from " & path, vbInformation
End Sub

Private Function SplitCSVLine(ByVal line As String) As String()
    ' Minimal CSV parser that supports quoted fields with commas inside.
    Dim out() As String
    ReDim out(0)
    Dim cur As String: cur = ""
    Dim inQ As Boolean: inQ = False
    Dim i As Long, ch As String
    For i = 1 To Len(line)
        ch = Mid$(line, i, 1)
        If inQ Then
            If ch = """" Then
                If i < Len(line) And Mid$(line, i + 1, 1) = """" Then
                    cur = cur & """"
                    i = i + 1
                Else
                    inQ = False
                End If
            Else
                cur = cur & ch
            End If
        Else
            If ch = """" Then
                inQ = True
            ElseIf ch = "," Then
                out(UBound(out)) = cur
                ReDim Preserve out(UBound(out) + 1)
                cur = ""
            Else
                cur = cur & ch
            End If
        End If
    Next i
    out(UBound(out)) = cur
    SplitCSVLine = out
End Function

' ============================================================
'  Monthly close-out snapshot                 (Tier 3)
' ============================================================

Public Sub CloseMonth()
    Dim monthStr As String
    monthStr = InputBox("Month to close (yyyy-mm):", "Close Month", Format$(Date, "yyyy-mm"))
    If Trim(monthStr) = "" Then Exit Sub
    If Len(monthStr) <> 7 Or Mid$(monthStr, 5, 1) <> "-" Then
        MsgBox "Expected format yyyy-mm, e.g. 2026-04.", vbExclamation: Exit Sub
    End If

    Dim folder As String
    folder = Application.ActiveWorkbook.Path & "\Archive"
    If Dir(folder, vbDirectory) = "" Then MkDir folder

    Dim outPath As String
    outPath = folder & "\MOCOH_DEMURRAGE_close_" & monthStr & ".xlsx"

    ' SaveCopyAs preserves macros (because source is xlsm).  We want a
    ' values-only frozen archive, so:
    '  1. Save a copy as the same xlsm in a temp location.
    '  2. Open the temp, paste-values everything, strip macros by saving as xlsx.
    Dim tmpPath As String
    tmpPath = Environ$("TEMP") & "\mocoh_close_tmp.xlsm"
    Application.DisplayAlerts = False
    ThisWorkbook.SaveCopyAs tmpPath
    Dim wb As Workbook: Set wb = Workbooks.Open(tmpPath)

    ' Freeze: paste-values across all sheets.
    Dim ws As Worksheet
    For Each ws In wb.Worksheets
        ws.Cells.Copy
        ws.Cells.PasteSpecial Paste:=xlPasteValuesAndNumberFormats
        Application.CutCopyMode = False
    Next ws

    ' Save as xlsx (no macros).
    wb.SaveAs Filename:=outPath, FileFormat:=xlOpenXMLWorkbook, _
              CreateBackup:=False
    wb.Close SaveChanges:=False
    Kill tmpPath
    Application.DisplayAlerts = True

    Call LogAudit("Workbook", "(close)", "month", "", monthStr, "Close month -> " & outPath)
    MsgBox "Frozen snapshot saved to:" & vbCrLf & outPath, vbInformation
End Sub
