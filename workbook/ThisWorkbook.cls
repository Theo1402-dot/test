Option Explicit

Private Sub Workbook_SheetChange(ByVal Sh As Object, ByVal Target As Range)
    If Sh.Name <> "Claims" Or Target.Cells.Count <> 1 Then Exit Sub
    If Target.Column <> 12 Or Target.Row < 7 Or Target.Row > 15 Then Exit Sub
    Application.EnableEvents = False
    Call LogAudit("Claims", Target.Address(False, False), "Status", _
                  "(prev)", CStr(Target.Value), "Manual edit")
    Application.EnableEvents = True
End Sub
