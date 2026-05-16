"""Inject two real Excel buttons (shapes with macros) on the Invoice
sheet so clicking them runs EmailClaim / PublishInvoicePDF.

The original drawing1.xml is attached to Invoice and contains only
images.  We append two <xdr:twoCellAnchor> shapes anchored at B36 and
E36, each with its `macro=` attribute referencing the public sub.
"""

from __future__ import annotations
import re
import zipfile
import shutil
import sys
import os


DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def make_button_xml(macro: str, label: str, color: str,
                    from_col: int, from_row: int,
                    to_col: int, to_row: int,
                    shape_id: int) -> str:
    """Return a <xdr:twoCellAnchor> element string for a labeled
    rounded-rectangle shape that triggers `macro` on click."""
    return f'''<xdr:twoCellAnchor>
  <xdr:from><xdr:col>{from_col}</xdr:col><xdr:colOff>50000</xdr:colOff>
            <xdr:row>{from_row}</xdr:row><xdr:rowOff>10000</xdr:rowOff></xdr:from>
  <xdr:to><xdr:col>{to_col}</xdr:col><xdr:colOff>-50000</xdr:colOff>
          <xdr:row>{to_row}</xdr:row><xdr:rowOff>-10000</xdr:rowOff></xdr:to>
  <xdr:sp macro="[0]!{macro}" textlink="">
    <xdr:nvSpPr>
      <xdr:cNvPr id="{shape_id}" name="{macro}Button"/>
      <xdr:cNvSpPr/>
    </xdr:nvSpPr>
    <xdr:spPr>
      <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></a:xfrm>
      <a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>
      <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
      <a:ln w="12700"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln>
      <a:effectLst>
        <a:outerShdw blurRad="40000" dist="20000" dir="5400000" rotWithShape="0">
          <a:srgbClr val="000000"><a:alpha val="20000"/></a:srgbClr>
        </a:outerShdw>
      </a:effectLst>
    </xdr:spPr>
    <xdr:style>
      <a:lnRef idx="0"><a:scrgbClr r="0" g="0" b="0"/></a:lnRef>
      <a:fillRef idx="0"><a:scrgbClr r="0" g="0" b="0"/></a:fillRef>
      <a:effectRef idx="0"><a:scrgbClr r="0" g="0" b="0"/></a:effectRef>
      <a:fontRef idx="minor"><a:schemeClr val="lt1"/></a:fontRef>
    </xdr:style>
    <xdr:txBody>
      <a:bodyPr vertOverflow="clip" horzOverflow="clip" wrap="square"
                lIns="36000" tIns="18000" rIns="36000" bIns="18000" anchor="ctr"/>
      <a:lstStyle/>
      <a:p>
        <a:pPr algn="ctr"/>
        <a:r>
          <a:rPr lang="en-US" sz="1200" b="1">
            <a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>
            <a:latin typeface="Calibri"/>
          </a:rPr>
          <a:t>{label}</a:t>
        </a:r>
      </a:p>
    </xdr:txBody>
  </xdr:sp>
  <xdr:clientData/>
</xdr:twoCellAnchor>'''


def add_invoice_buttons(src_xlsm: str, dst_xlsm: str) -> None:
    """Read src_xlsm, append two macro buttons to its Invoice drawing,
    write to dst_xlsm."""
    with zipfile.ZipFile(src_xlsm, "r") as zin:
        names = zin.namelist()
        drawing_xml = zin.read("xl/drawings/drawing1.xml").decode("utf-8")

    # Excel anchors are (col, colOff, row, rowOff).  Row 36 cell on the
    # sheet is row index 35 (0-based) in the drawing namespace.  Span
    # button across 2 cells, height 1 row.
    btn_email = make_button_xml(
        macro="EmailClaim", label="Open Email Draft", color="1F4E79",
        from_col=1, from_row=35, to_col=3, to_row=36, shape_id=1001,
    )
    btn_pdf = make_button_xml(
        macro="PublishInvoicePDF", label="Publish PDF", color="047857",
        from_col=4, from_row=35, to_col=6, to_row=36, shape_id=1002,
    )

    # Insert before the closing </xdr:wsDr>.
    close_tag = "</xdr:wsDr>"
    if close_tag not in drawing_xml:
        raise RuntimeError("drawing1.xml missing closing wsDr tag")
    new_drawing = drawing_xml.replace(close_tag, btn_email + btn_pdf + close_tag)

    # Write everything to the new zip, replacing drawing1.xml.
    with zipfile.ZipFile(src_xlsm, "r") as zin, \
         zipfile.ZipFile(dst_xlsm, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            if name == "xl/drawings/drawing1.xml":
                zout.writestr(name, new_drawing)
            else:
                zout.writestr(name, zin.read(name))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: add_invoice_buttons.py <in.xlsm> <out.xlsm>", file=sys.stderr)
        sys.exit(2)
    add_invoice_buttons(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]}")
