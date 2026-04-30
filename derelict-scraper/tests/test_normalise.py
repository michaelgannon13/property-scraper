import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import utils


def test_normalise_dataframe_produces_correct_row():
    df = pd.DataFrame({
        "ds_ref": ["DS001"],
        "address": ["1 Main St"],
        "owner": ["Alice"],
        "date_entered_register": ["25/06/2020"],
        "valuation": ["€12,500"],
    })
    rows = utils.normalise_dataframe(df, "SDCC", "test.xlsx")
    assert len(rows) == 1
    row = rows[0]
    assert row["council"] == "SDCC"
    assert row["ds_ref"] == "DS001"
    assert row["date_entered_register"] == "2020-06-25"
    assert row["valuation"] == 12500.0
    assert row["days_on_register"] is not None
    assert row["days_on_register"] > 0
    assert row["raw_source_file"] == "test.xlsx"


def test_normalise_dataframe_fills_missing_fields_with_none():
    df = pd.DataFrame({"ds_ref": ["DS002"]})
    rows = utils.normalise_dataframe(df, "TEST", "x.xlsx")
    assert rows[0]["address"] is None
    assert rows[0]["owner"] is None


def test_normalise_dataframe_skips_fully_empty_rows():
    df = pd.DataFrame({
        "ds_ref": [None, "DS001"],
        "address": [None, "1 Main St"],
    })
    rows = utils.normalise_dataframe(df, "TEST", "x.xlsx")
    assert len(rows) == 1
