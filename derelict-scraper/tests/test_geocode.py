import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import database
import geocode


# --- helpers ---

def _seed_row(conn, ds_ref="DS001", address="1 Main St", council="TEST", lat=None, lng=None):
    conn.execute(
        """INSERT INTO derelict_sites
           (council, ds_ref, address, reg_no, owner, owner_address, occupier,
            electoral_area, date_entered_register, valuation, valuation_date,
            days_on_register, last_updated, raw_source_file)
           VALUES (?,?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)""",
        (council, ds_ref, address),
    )
    if lat is not None:
        conn.execute(
            "UPDATE derelict_sites SET lat=?, lng=? WHERE council=? AND ds_ref=?",
            (lat, lng, council, ds_ref),
        )
    conn.commit()


def _nominatim_ok(lat=53.3, lon=-6.2):
    resp = MagicMock()
    resp.json.return_value = [{"lat": str(lat), "lon": str(lon), "display_name": "Dublin"}]
    return resp


def _nominatim_empty():
    resp = MagicMock()
    resp.json.return_value = []
    return resp


def _google_ok(lat=53.3, lng=-6.2):
    resp = MagicMock()
    resp.json.return_value = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": lat, "lng": lng}}}],
    }
    return resp


# --- clean_address ---

def test_clean_address_strips_newlines():
    assert geocode.clean_address("38 Main St\nDublin 4") == "38 Main St, Dublin 4"


def test_clean_address_removes_smart_quotes():
    result = geocode.clean_address("‘Capri’ House, Dublin")
    assert "‘" not in result
    assert "’" not in result


def test_clean_address_normalises_whitespace():
    assert geocode.clean_address("1  Main   St") == "1 Main St"


# --- extract_eircode ---

def test_extract_eircode_finds_embedded_code():
    assert geocode.extract_eircode("38 Russell Crescent\nD24 NN82") == "D24 NN82"


def test_extract_eircode_handles_no_space():
    assert geocode.extract_eircode("Some Address D6WXY12") == "D6W XY12"


def test_extract_eircode_returns_none_when_absent():
    assert geocode.extract_eircode("1 Main Street, Dublin") is None


# --- geocode_with_nominatim ---

def test_geocode_with_nominatim_returns_coords():
    session = MagicMock()
    session.get.return_value = _nominatim_ok(53.3, -6.2)
    lat, lng = geocode.geocode_with_nominatim("D24 NN82, Ireland", session)
    assert lat == 53.3
    assert lng == -6.2


def test_geocode_with_nominatim_returns_none_on_empty():
    session = MagicMock()
    session.get.return_value = _nominatim_empty()
    lat, lng = geocode.geocode_with_nominatim("Nowhere", session)
    assert lat is None and lng is None


def test_geocode_with_nominatim_returns_none_on_error():
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    lat, lng = geocode.geocode_with_nominatim("test", session)
    assert lat is None and lng is None


# --- geocode_address strategy ---

def test_geocode_address_uses_eircode_first(monkeypatch):
    monkeypatch.setattr(geocode, "_NOMINATIM_DELAY", 0)
    session = MagicMock()
    session.get.return_value = _nominatim_ok(53.3, -6.2)

    lat, lng = geocode.geocode_address("1 Main St\nD24 NN82", session, api_key=None)

    # First call should be the Eircode query
    first_call_params = session.get.call_args_list[0].kwargs["params"]["q"]
    assert "D24 NN82" in first_call_params
    assert lat == 53.3


def test_geocode_address_falls_back_to_full_address_when_eircode_fails(monkeypatch):
    monkeypatch.setattr(geocode, "_NOMINATIM_DELAY", 0)
    session = MagicMock()
    session.get.side_effect = [_nominatim_empty(), _nominatim_ok(53.3, -6.2)]

    lat, lng = geocode.geocode_address("1 Main St\nD24 NN82", session, api_key=None)
    assert lat == 53.3
    assert session.get.call_count == 2


def test_geocode_address_falls_back_to_google(monkeypatch):
    monkeypatch.setattr(geocode, "_NOMINATIM_DELAY", 0)
    monkeypatch.setattr(geocode, "_GOOGLE_DELAY", 0)
    session = MagicMock()
    # No Eircode in address → only 1 Nominatim call, then Google
    session.get.side_effect = [_nominatim_empty(), _google_ok(53.3, -6.2)]

    lat, lng = geocode.geocode_address("1 Main St", session, api_key="FAKE_KEY")
    assert lat == 53.3


def test_geocode_address_returns_none_when_all_fail(monkeypatch):
    monkeypatch.setattr(geocode, "_NOMINATIM_DELAY", 0)
    session = MagicMock()
    session.get.return_value = _nominatim_empty()
    lat, lng = geocode.geocode_address("Unparseable address ????", session, api_key=None)
    assert lat is None and lng is None


# --- run() integration ---

def test_run_updates_null_rows(tmp_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "FAKE")
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    monkeypatch.setattr(geocode, "_NOMINATIM_DELAY", 0)
    database.init_db()
    conn = database.get_connection()
    _seed_row(conn, "DS001", "1 Main St")

    with patch("requests.Session") as mock_session_cls:
        mock_session_cls.return_value.get.return_value = _nominatim_ok(53.3, -6.2)
        geocode.run()

    row = conn.execute("SELECT lat, lng FROM derelict_sites WHERE ds_ref='DS001'").fetchone()
    assert row[0] == 53.3
    assert row[1] == -6.2


def test_run_skips_already_geocoded(tmp_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "FAKE")
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    conn = database.get_connection()
    _seed_row(conn, "DS001", "1 Main St", lat=99.0, lng=99.0)

    with patch("requests.Session") as mock_session_cls:
        geocode.run()
        mock_session_cls.return_value.get.assert_not_called()


def test_run_handles_failed_geocode_gracefully(tmp_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "FAKE")
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    monkeypatch.setattr(geocode, "_NOMINATIM_DELAY", 0)
    database.init_db()
    conn = database.get_connection()
    _seed_row(conn, "DS001", "Unparseable Address ????")

    with patch("requests.Session") as mock_session_cls:
        mock_session_cls.return_value.get.return_value = _nominatim_empty()
        geocode.run()  # must not raise

    row = conn.execute("SELECT lat FROM derelict_sites WHERE ds_ref='DS001'").fetchone()
    assert row[0] is None


def test_run_works_without_google_key(tmp_db, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    monkeypatch.setattr(geocode, "_NOMINATIM_DELAY", 0)
    database.init_db()
    conn = database.get_connection()
    _seed_row(conn, "DS001", "1 Main St")

    with patch("requests.Session") as mock_session_cls:
        mock_session_cls.return_value.get.return_value = _nominatim_ok(53.3, -6.2)
        geocode.run()  # should not raise even without Google key

    row = conn.execute("SELECT lat FROM derelict_sites WHERE ds_ref='DS001'").fetchone()
    assert row[0] == 53.3
