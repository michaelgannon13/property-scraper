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
