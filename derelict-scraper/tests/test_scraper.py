import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.base import GenericScraper, _score_link


def make_scraper(hints=None, page_url="https://example.ie/derelict"):
    config = {
        "council_code": "TEST",
        "page_url": page_url,
        "hints": hints or {"selector": None, "url_contains": None, "direct_url": None},
    }
    session = MagicMock()
    return GenericScraper(config, session)


def test_score_link_excel_keyword():
    score = _score_link("/files/derelict-register.xlsx", "Download Register")
    assert score >= 5


def test_score_link_no_match():
    assert _score_link("/contact-us", "Contact Us") == 0


def test_find_link_direct_url_skips_page_fetch():
    scraper = make_scraper(hints={"direct_url": "https://example.ie/register.xlsx",
                                  "selector": None, "url_contains": None})
    result = scraper.find_link()
    assert result == "https://example.ie/register.xlsx"
    scraper.session.get.assert_not_called()


def test_find_link_url_contains():
    html = '<html><body><a href="/files/derelict-register.xlsx">Register</a></body></html>'
    scraper = make_scraper(hints={"selector": None, "url_contains": ".xlsx", "direct_url": None})
    scraper.session.get.return_value.text = html
    scraper.session.get.return_value.raise_for_status = MagicMock()
    result = scraper.find_link()
    assert result.endswith(".xlsx")


def test_find_link_heuristic_scores_correctly():
    html = """<html><body>
        <a href="/about">About Us</a>
        <a href="/files/derelict-sites-register-2024.xlsx">Derelict Sites Register 2024</a>
    </body></html>"""
    scraper = make_scraper(hints={"selector": None, "url_contains": None, "direct_url": None})
    scraper.session.get.return_value.text = html
    scraper.session.get.return_value.raise_for_status = MagicMock()
    result = scraper.find_link()
    assert "derelict" in result.lower()
    assert result.endswith(".xlsx")


def test_find_link_returns_none_when_no_candidates():
    html = "<html><body><a href='/about'>About</a></body></html>"
    scraper = make_scraper()
    scraper.session.get.return_value.text = html
    scraper.session.get.return_value.raise_for_status = MagicMock()
    result = scraper.find_link()
    assert result is None
