"""Invoice PDF rendering. Integration test is skipped when neither xlwings nor
a working `soffice` is available — that lets the suite stay green on stripped
containers while still verifying the helpers end-to-end on Theo's machine.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from demurrage import config as cfg
from demurrage.invoice_pdf import (
    _invoice_no_from_claim,
    _slugify_consignee,
    invoice_pdf_path,
    render_invoice_pdf,
)


# ---------- pure helpers ----------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Rubis Energy Zambia", "RubisEnergyZambia"),
        ("La Grace De Dieu Avec Nous Sarl", "LaGraceDeDieuAvecNousSarl"),
        ("ARV Energy", "ArvEnergy"),
        ("Lake Petroleum  Zambia ", "LakePetroleumZambia"),
        ("Reliance & Co. Ltd", "RelianceCoLtd"),
        ("", "Consignee"),
        ("---", "Consignee"),
    ],
)
def test_slugify_consignee(name, expected):
    assert _slugify_consignee(name) == expected


def test_invoice_no_from_claim():
    assert _invoice_no_from_claim("187296-DEM") == "MOC-DEM-2026-187296"
    assert _invoice_no_from_claim("184182-DEM") == "MOC-DEM-2026-184182"
    # Idempotent when the claim already carries the full prefix.
    assert _invoice_no_from_claim("MOC-DEM-2026-999") == "MOC-DEM-2026-999"


def test_invoice_pdf_path_format(tmp_path: Path):
    p = invoice_pdf_path(
        "187296-DEM", "Rubis Energy Zambia",
        issue_date=date(2026, 5, 20), output_dir=tmp_path,
    )
    assert p == tmp_path / "MOC-DEM-2026-187296_RubisEnergyZambia_2026-05-20.pdf"
    assert tmp_path.exists()


# ---------- integration: actually render a PDF ----------


def _renderer_available() -> bool:
    if sys.platform == "win32":
        try:
            import xlwings  # noqa: F401
            return True
        except ImportError:
            return False
    if not shutil.which("soffice") and not shutil.which("libreoffice"):
        return False
    # libreoffice-core without -calc silently fails on every spreadsheet; smoke-
    # test with a tiny file before claiming we can render.
    from openpyxl import Workbook
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "probe.xlsx"
        wb = Workbook()
        wb.active["A1"] = "probe"
        wb.save(src)
        try:
            proc = subprocess.run(
                ["soffice", f"-env:UserInstallation=file://{Path(d) / 'prof'}",
                 "--headless", "--convert-to", "pdf", "--outdir", d, str(src)],
                capture_output=True, text=True, timeout=60,
            )
        except Exception:
            return False
        return (Path(d) / "probe.pdf").exists() and proc.returncode == 0


@pytest.mark.skipif(
    not _renderer_available(),
    reason="no working PDF renderer (xlwings on win32 or libreoffice-calc on others)",
)
def test_render_invoice_pdf_end_to_end(tmp_path: Path):
    out = render_invoice_pdf(
        "187296-DEM",
        output_dir=tmp_path,
        issue_date=date(2026, 5, 20),
    )
    assert out.exists()
    assert out.stat().st_size > 1024, "PDF should be more than 1 KB"
    assert out.name == "MOC-DEM-2026-187296_RubisEnergyZambia_2026-05-20.pdf"

    # If pdftotext is around, verify the right claim landed in the file
    # (catches B20 not being driven correctly).
    if shutil.which("pdftotext"):
        text = subprocess.run(
            ["pdftotext", str(out), "-"], capture_output=True, text=True, timeout=30,
        ).stdout
        assert "187296-DEM" in text, "claim_no must appear in the rendered PDF"
        assert "Rubis Energy Zambia" in text
        assert "MOCOH SA" in text
