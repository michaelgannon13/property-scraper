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

    def find_link(self) -> Optional[str]:
        if self.hints.get("direct_url"):
            return self.hints["direct_url"]

        resp = self.session.get(self.config["page_url"], timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
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
            score = _score_link(a["href"], a.get_text(" ", strip=True))
            if score > 0:
                candidates.append((score, a))

        if not candidates:
            return None

        best_score = max(s for s, _ in candidates)
        best = [a for s, a in candidates if s == best_score]
        return urljoin(base, best[-1]["href"])
