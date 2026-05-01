import re
import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("derelict.scraper")

_KEYWORDS = ["register", "derelict", "sites"]
_EXTENSIONS = [".xlsx", ".xls", ".csv", ".pdf"]
_YEAR_RE = re.compile(r"20\d{2}")


def _score_link(href: str, text: str) -> int:
    score = 0
    combined = (href + " " + text).lower()
    for kw in _KEYWORDS:
        if kw in combined:
            score += 2
    for ext in _EXTENSIONS:
        if href.lower().endswith(ext) or (ext + "?") in href.lower():
            score += 3
    if _YEAR_RE.search(combined):
        score += 1
    return score


class GenericScraper:
    def __init__(self, config: dict, session: requests.Session):
        self.config = config
        self.session = session
        self.hints = config.get("hints") or {}
        self._log = logging.getLogger(f"derelict.scraper.{config['council_code']}")

    def _find_link_playwright(self) -> Optional[str]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "playwright not installed; run: pip install playwright && playwright install chromium"
            )
        base = self.config["page_url"]
        url_contains = (self.hints.get("url_contains") or "").lower()
        selector = self.hints.get("selector")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(base, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=30000)

                if selector:
                    el = page.query_selector(selector)
                    if el:
                        href = el.get_attribute("href") or ""
                        if href:
                            return urljoin(base, href)

                links = page.query_selector_all("a[href]")
                candidates = []
                for link in links:
                    href = link.get_attribute("href") or ""
                    text = link.inner_text()
                    full = (href + " " + text).lower()
                    if url_contains and url_contains in full:
                        return urljoin(base, href)
                    score = _score_link(href, text)
                    if score > 0:
                        candidates.append((score, href))

                if not candidates:
                    return None
                best_score = max(s for s, _ in candidates)
                best = [h for s, h in candidates if s == best_score]
                return urljoin(base, best[-1])
            finally:
                browser.close()

    def find_link(self) -> Optional[str]:
        if self.hints.get("direct_url"):
            return self.hints["direct_url"]

        if self.hints.get("js_render"):
            return self._find_link_playwright()

        resp = self.session.get(self.config["page_url"], timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        base = self.config["page_url"]

        if self.hints.get("selector"):
            el = soup.select_one(self.hints["selector"])
            if el and el.get("href"):
                return urljoin(base, el["href"])

        if self.hints.get("url_contains"):
            needle = self.hints["url_contains"].lower()
            for a in soup.find_all("a", href=True):
                if needle in a["href"].lower():
                    return urljoin(base, a["href"])

        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith(("http", "/", ".")):
                continue
            score = _score_link(href, a.get_text(" ", strip=True))
            if score > 0:
                candidates.append((score, a))

        if not candidates:
            return None

        best_score = max(s for s, _ in candidates)
        best = [a for s, a in candidates if s == best_score]
        return urljoin(base, best[-1]["href"])
