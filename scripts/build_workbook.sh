#!/usr/bin/env bash
# Build the fully-upgraded MOCOH demurrage workbook in one go.
#
# Pipeline:
#   1. upgrade_demurrage_xlsm.py  -- cell content (Consignees Cc col, remove
#                                    invoice body cells, print areas, Macros
#                                    sheet instructions).
#   2. inject_vba.py              -- write our Module1 + ThisWorkbook code
#                                    into the existing vbaProject.bin so the
#                                    macros are installed (no manual paste).
#   3. add_invoice_buttons.py     -- inject two clickable shapes on Invoice
#                                    bound to EmailClaim / PublishInvoicePDF.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
SRC="$REPO/workbook/MOCOH_DEMURRAGE_2026.xlsm"
OUT="$REPO/workbook/MOCOH_DEMURRAGE_2026_v5.xlsm"
TMP1="$(mktemp --suffix=.xlsm)"
TMP2="$(mktemp --suffix=.xlsm)"
TMP3="$(mktemp --suffix=.xlsm)"
TMP4="$(mktemp --suffix=.xlsm)"
trap 'rm -f "$TMP1" "$TMP2" "$TMP3" "$TMP4"' EXIT

python3 "$HERE/upgrade_demurrage_xml.py"    "$SRC"  "$TMP1"
python3 "$HERE/upgrade_v4_xml.py"           "$TMP1" "$TMP2"
python3 "$HERE/upgrade_v5_xml.py"           "$TMP2" "$TMP3"
python3 "$HERE/inject_vba.py"               "$TMP3" "$TMP4" \
    --module Module1="$REPO/workbook/Module1.bas" \
    --module ThisWorkbook="$REPO/workbook/ThisWorkbook.cls"
python3 "$HERE/add_invoice_buttons.py"      "$TMP4" "$OUT"

echo "wrote $OUT"
