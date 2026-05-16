Option Explicit

' ============================================================
'  MOCOH Demurrage 2026 -- Workflow macros (auto-installed)
'  Buttons on Cover / Invoice / Claims sheets call these subs.
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
'    Exports Invoice + Annex tabs to a single PDF file.
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
'    Opens Outlook with To / Cc / Subject / Body pre-filled and
'    attaches a freshly-exported Invoice PDF.  The draft is shown
'    (not sent) so it can be reviewed first.
' ------------------------------------------------------------
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
    Call LogAudit("Invoice", "B20", "Email", "", claimNo, "Open Outlook draft")
End Sub

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
