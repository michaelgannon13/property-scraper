import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import utils


def test_parse_date_slash_dmy():
    assert utils.parse_date("25/06/2021") == "2021-06-25"


def test_parse_date_dash_dmy():
    assert utils.parse_date("25-06-2021") == "2021-06-25"


def test_parse_date_iso():
    assert utils.parse_date("2021-06-25") == "2021-06-25"


def test_parse_date_none_returns_none():
    assert utils.parse_date(None) is None


def test_parse_date_empty_returns_none():
    assert utils.parse_date("") is None


def test_parse_date_nan_returns_none():
    assert utils.parse_date("nan") is None


def test_parse_valuation_strips_euro_and_commas():
    assert utils.parse_valuation("€12,500.00") == 12500.0


def test_parse_valuation_plain_number():
    assert utils.parse_valuation("50000") == 50000.0


def test_parse_valuation_none_returns_none():
    assert utils.parse_valuation(None) is None


def test_parse_valuation_non_numeric_returns_none():
    assert utils.parse_valuation("N/A") is None


def test_days_since_known_date(monkeypatch):
    from datetime import date
    monkeypatch.setattr(utils, "_today", lambda: date(2024, 1, 1))
    assert utils.days_since("2023-01-01") == 365


def test_days_since_none_returns_none():
    assert utils.days_since(None) is None


def test_run_id_format():
    rid = utils.run_id()
    assert len(rid) == 19
    assert rid[10] == "_"


# --- classify_property_type ---

def test_classify_apartment():
    assert utils.classify_property_type("Apartment 4, Mill Lane") == "Apartment"


def test_classify_cottage():
    assert utils.classify_property_type("2 Rose Cottages, Ballina") == "Cottage"


def test_classify_house():
    assert utils.classify_property_type("Derelict House, Main Street") == "House"


def test_classify_industrial_warehouse():
    assert utils.classify_property_type("Old Warehouse, North Quay") == "Industrial"


def test_classify_industrial_distillery():
    assert utils.classify_property_type("Former Distillery, Watercourse Road") == "Industrial"


def test_classify_institutional_church():
    assert utils.classify_property_type("St Mary's Church, Ballyhaunis") == "Institutional"


def test_classify_institutional_convent():
    assert utils.classify_property_type("Former Good Shepherd Convent Site") == "Institutional"


def test_classify_commercial_pub():
    assert utils.classify_property_type("Kennedy's Bar, Main Street") == "Commercial"


def test_classify_commercial_hotel():
    assert utils.classify_property_type("The Grand Hotel, Malahide") == "Commercial"


def test_classify_vacant_land():
    assert utils.classify_property_type("Site at South Douglas Road") == "Vacant Land"


def test_classify_other_plain_address():
    assert utils.classify_property_type("14 Patrick Street, Drogheda") == "Other"


def test_classify_none_returns_other():
    assert utils.classify_property_type(None) == "Other"


def test_classify_no_false_positive_bar_in_barrack():
    # "Barrack" contains "bar" as substring — must not match Commercial
    assert utils.classify_property_type("64 Barrack Street, Dundalk") == "Other"


def test_classify_cottage_beats_site():
    # "Site comprising cottages" — Cottage should win over Vacant Land
    assert utils.classify_property_type("Site comprising of 6 & 7 Bramble Cottages") == "Cottage"
