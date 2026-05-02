import sys
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import database
import geocode


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


def _mock_ok_response(lat=53.3, lng=-6.2):
    resp = MagicMock()
    resp.json.return_value = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": lat, "lng": lng}}}],
    }
    return resp


def _mock_zero_results():
    resp = MagicMock()
    resp.json.return_value = {"status": "ZERO_RESULTS", "results": []}
    return resp


def test_geocode_address_returns_lat_lng():
    session = MagicMock()
    session.get.return_value = _mock_ok_response(53.3, -6.2)
    lat, lng = geocode.geocode_address("1 Main St", session, "FAKE_KEY")
    assert lat == 53.3
    assert lng == -6.2
    call_params = session.get.call_args
    assert "Ireland" in call_params.kwargs["params"]["address"]


def test_geocode_address_zero_results_returns_none():
    session = MagicMock()
    session.get.return_value = _mock_zero_results()
    lat, lng = geocode.geocode_address("Nowhere", session, "FAKE_KEY")
    assert lat is None
    assert lng is None


def test_run_updates_null_rows(tmp_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "FAKE")
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    conn = database.get_connection()
    _seed_row(conn, "DS001", "1 Main St")
    _seed_row(conn, "DS002", "2 Side St")

    mock_session = MagicMock()
    mock_session.get.return_value = _mock_ok_response(53.3, -6.2)

    with patch("requests.Session", return_value=mock_session):
        geocode.run()

    rows = conn.execute("SELECT lat, lng FROM derelict_sites WHERE council='TEST'").fetchall()
    assert all(r[0] == 53.3 and r[1] == -6.2 for r in rows)


def test_run_skips_already_geocoded(tmp_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "FAKE")
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    conn = database.get_connection()
    _seed_row(conn, "DS001", "1 Main St", lat=99.0, lng=99.0)

    mock_session = MagicMock()
    with patch("requests.Session", return_value=mock_session):
        geocode.run()

    # Session.get should never have been called for an already-geocoded row
    mock_session.get.assert_not_called()


def test_run_handles_failed_geocode_gracefully(tmp_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "FAKE")
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    conn = database.get_connection()
    _seed_row(conn, "DS001", "Unparseable Address ????")

    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("network error")

    with patch("requests.Session", return_value=mock_session):
        geocode.run()  # must not raise

    row = conn.execute("SELECT lat FROM derelict_sites WHERE ds_ref='DS001'").fetchone()
    assert row[0] is None  # lat stays NULL after failure


def test_run_exits_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        geocode.run()
