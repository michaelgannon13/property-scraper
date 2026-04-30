import pytest
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers import pdf_parser


COLUMN_MAP = {
    "Site Ref": "ds_ref",
    "Address": "address",
    "Owner": "owner",
}


def test_parse_uses_pdfplumber_result(tmp_path, monkeypatch):
    fake_df = pd.DataFrame({
        "Site Ref": ["DS001"],
        "Address": ["1 Main St"],
        "Owner": ["Alice"],
    })
    monkeypatch.setattr(pdf_parser, "_extract_with_pdfplumber", lambda _: fake_df)
    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 fake")
    result = pdf_parser.parse(dummy_pdf, COLUMN_MAP)
    assert "ds_ref" in result.columns
    assert result.iloc[0]["address"] == "1 Main St"


def test_parse_falls_back_to_tabula_when_pdfplumber_empty(tmp_path, monkeypatch):
    fake_df = pd.DataFrame({
        "Site Ref": ["DS002"],
        "Address": ["2 Side St"],
        "Owner": ["Bob"],
    })
    monkeypatch.setattr(pdf_parser, "_extract_with_pdfplumber", lambda _: pd.DataFrame())
    monkeypatch.setattr(pdf_parser, "_extract_text_fallback", lambda _: pd.DataFrame())
    monkeypatch.setattr(pdf_parser, "_extract_with_tabula", lambda _: fake_df)
    dummy_pdf = tmp_path / "dummy2.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 fake")
    result = pdf_parser.parse(dummy_pdf, COLUMN_MAP)
    assert result.iloc[0]["ds_ref"] == "DS002"


def test_parse_raises_when_both_extractors_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_parser, "_extract_with_pdfplumber", lambda _: pd.DataFrame())
    monkeypatch.setattr(pdf_parser, "_extract_text_fallback", lambda _: pd.DataFrame())
    monkeypatch.setattr(pdf_parser, "_extract_with_tabula", lambda _: pd.DataFrame())
    dummy_pdf = tmp_path / "dummy3.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(ValueError, match="Could not extract"):
        pdf_parser.parse(dummy_pdf, COLUMN_MAP)
