import pytest
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers import excel_parser


def test_parse_excel_basic(tmp_path, sample_column_map):
    wb_path = tmp_path / "test.xlsx"
    df = pd.DataFrame({
        "Site Ref": ["DS001", "DS002"],
        "Reg No": ["R1", "R2"],
        "Address": ["1 Main St", "2 Main St"],
        "Owner": ["Alice", "Bob"],
        "Owner Address": [None, None],
        "Occupier": [None, None],
        "Electoral Area": ["Area A", "Area B"],
        "Date Entered": ["25/06/2021", "01/01/2022"],
        "Valuation": ["€12,500", "€25,000"],
        "Valuation Date": [None, None],
    })
    df.to_excel(wb_path, index=False)
    result = excel_parser.parse(wb_path, sample_column_map)
    assert len(result) == 2
    assert "ds_ref" in result.columns
    assert "address" in result.columns
    assert result.iloc[0]["ds_ref"] == "DS001"


def test_parse_detects_header_after_junk_rows(tmp_path, sample_column_map):
    wb_path = tmp_path / "test_junk.xlsx"
    junk = pd.DataFrame([
        ["Council Derelict Sites Register 2024", None, None, None, None, None, None, None, None, None],
        ["Published by Planning Dept", None, None, None, None, None, None, None, None, None],
        ["Site Ref", "Reg No", "Address", "Owner", "Owner Address", "Occupier",
         "Electoral Area", "Date Entered", "Valuation", "Valuation Date"],
        ["DS001", "R1", "1 Main St", "Alice", None, None, "Area A", "25/06/2021", "€12,500", None],
    ])
    junk.to_excel(wb_path, index=False, header=False)
    result = excel_parser.parse(wb_path, sample_column_map)
    assert len(result) >= 1
    assert "ds_ref" in result.columns


def test_parse_csv_basic(tmp_path, sample_column_map):
    csv_path = tmp_path / "test.csv"
    df = pd.DataFrame({
        "Site Ref": ["DS001"],
        "Reg No": ["R1"],
        "Address": ["1 Main St"],
        "Owner": ["Alice"],
        "Owner Address": [None],
        "Occupier": [None],
        "Electoral Area": ["Area A"],
        "Date Entered": ["25/06/2021"],
        "Valuation": ["€12,500"],
        "Valuation Date": [None],
    })
    df.to_csv(csv_path, index=False)
    result = excel_parser.parse(csv_path, sample_column_map)
    assert len(result) == 1
    assert result.iloc[0]["address"] == "1 Main St"


def test_parse_raises_on_unrecognised_columns(tmp_path):
    wb_path = tmp_path / "bad.xlsx"
    df = pd.DataFrame({"Foo": [1], "Bar": [2]})
    df.to_excel(wb_path, index=False)
    with pytest.raises(ValueError, match="No recognised columns"):
        excel_parser.parse(wb_path, {})
