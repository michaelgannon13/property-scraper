import pytest
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def sample_column_map():
    return {
        "Site Ref": "ds_ref",
        "Reg No": "reg_no",
        "Address": "address",
        "Owner": "owner",
        "Owner Address": "owner_address",
        "Occupier": "occupier",
        "Electoral Area": "electoral_area",
        "Date Entered": "date_entered_register",
        "Valuation": "valuation",
        "Valuation Date": "valuation_date",
    }
