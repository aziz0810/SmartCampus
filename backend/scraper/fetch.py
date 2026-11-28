from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup, Comment
from pypdf import PdfReader

from scraper.config import (
    BASE_URL,
    MAX_PAGES,
    MAX_RETRIES,
    MIN_REQUEST_INTERVAL_SECONDS,
    SANITIZED_CACHE_DIR,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_SECONDS,
    ROBOTS_URL,
    SEED_PAGES,
    ScraperSettings,
    is_same_domain,
)

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+216[ .]?)?(?:[2-9]\d{7}|[2-9]\d(?:[ .]\d{3}){2})(?!\d)")
BANK_RE = re.compile(r"\b(?:IBAN|SWIFT|BIC|RIB|bank account|compte bancaire|virement bancaire)\b", re.I)
ACCOUNT_NUMBER_RE = re.compile(r"(?<!\d)(?:TN\s*)?\d(?:[ .-]?\d){19,30}(?!\d)", re.I)
NEWS_RE = re.compile(r"actualit|news|erasmus|main candidate|reserve candidate|not selected|full name|GPA", re.I)
NEWS_HEADING_RE = re.compile(r"actualit|news|erasmus|selected candidates?|results", re.I)
SENSITIVE_CLASS_RE = re.compile(
    r"(?:^|[\s_-])(?:footer|contact|author|staff|team|news|actualit\w*|erasmus|social|menu|navigation|profile)(?=$|[\s_-])",
    re.I,
)
PORTAL_RE = re.compile(r"login|moodle|sso|webmail|email-portal", re.I)
SANITIZER_VERSION = 3


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    content: str
    content_hash: str
    consulted_on: str
    content_type: str
    cached: bool


def sanitize_text(value: str) -> str:
    value = EMAIL_RE.sub("", value)
    value = PHONE_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def sanitize_html(raw_html: str, source_url: str) -> str:
    soup = BeautifulSoup(raw_html, "lxml")
    for node in soup.find_all(["script", "style", "noscript", "iframe", "nav", "header", "footer", "aside", "form", "svg"]):
        node.decompose()
    for node in list(soup.find_all(True)):
        if node.name in {"html", "body"}:
            continue
        if node.attrs is None:
            continue
        label = " ".join([str(node.get("id", "")), " ".join(node.get("class", []))])
        if SENSITIVE_CLASS_RE.search(label):
            node.decompose()
    for table in list(soup.find_all("table")):
        table_text = table.get_text(" ", strip=True)
        is_fee_page = source_url.rstrip("/").endswith("procedure-et-frais-dinscription")
        if NEWS_RE.search(table_text) or (
            is_fee_page and (BANK_RE.search(table_text) or ACCOUNT_NUMBER_RE.search(table_text))
        ):
            table.decompose()
    for node in list(soup.find_all(["section", "article", "div"])):
        # Remove a complete builder section if it is an unrelated news, staff,
        # contact, or student-results panel.
        if node.attrs is None:
            continue
        label = " ".join([str(node.get("id", "")), " ".join(node.get("class", []))])
        if SENSITIVE_CLASS_RE.search(label):
            node.decompose()
            continue
    for node in list(soup.select(".bt_bb_section, .elementor-section")):
        heading = node.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading and NEWS_HEADING_RE.search(heading.get_text(" ", strip=True)):
            node.decompose()
    for anchor in list(soup.find_all("a", href=True)):
        href = str(anchor.get("href", ""))
        if href.lower().startswith(("mailto:", "tel:")) or PORTAL_RE.search(href):
            anchor.decompose()
        elif EMAIL_RE.search(href) or PHONE_RE.search(href):
            anchor.decompose()
    for node in list(soup.find_all(["p", "li", "td", "th", "tr"])):
        text = node.get_text(" ", strip=True)
        if re.search(r"\b(?:M\.|Mme|Mrs\.?|Mr\.?|Dr\.?|Pr\.?)\s+[A-ZÀ-Ÿ]", text):
            node.decompose()
        elif source_url.rstrip("/").endswith("procedure-et-frais-dinscription") and (
            BANK_RE.search(text) or ACCOUNT_NUMBER_RE.search(text)
        ):
            node.decompose()
    for table in list(soup.find_all("table")):
        labels = " ".join(th.get_text(" ", strip=True) for th in table.find_all("th"))
        if NEWS_RE.search(labels) or re.search(r"candidate|nom complet|full name|email|téléphone", labels, re.I):
            table.decompose()
    for node in soup.find_all(True):
        for attribute, value in list(node.attrs.items()):
            values = value if isinstance(value, list) else [value]
            if any(EMAIL_RE.search(str(item)) or PHONE_RE.search(str(item)) for item in values):
                del node.attrs[attribute]
    for text_node in list(soup.find_all(string=True)):
        if isinstance(text_node, Comment):
            text_node.extract()
            continue
        cleaned = sanitize_text(str(text_node))
        if cleaned != str(text_node):
            text_node.replace_with(cleaned)
    return str(soup)


def sanitize_pdf_text(text: str) -> str:
    safe_lines = []
    for line in text.splitlines():
        if BANK_RE.search(line) or ACCOUNT_NUMBER_RE.search(line) or NEWS_RE.search(line):
            continue
        if re.search(r"\b(?:M\.|Mme|Mrs\.?|Mr\.?|Dr\.?|Pr\.?)\s+[A-ZÀ-Ÿ]", line):
            continue
        cleaned = sanitize_text(line)
        if cleaned:
            safe_lines.append(cleaned)
    return "\n".join(safe_lines)


class PoliteFetcher:
    def __init__(
        self,
        settings: ScraperSettings,
        cache_dir: Path = SANITIZED_CACHE_DIR,
        client: httpx.Client | None = None,
        min_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
        max_pages: int = MAX_PAGES,
    ) -> None:
        self.settings = settings
        self.cache_dir = cache_dir
        self.client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)
        self._owns_client = client is None
        self.min_interval = min_interval
        self.max_pages = max_pages
        self._last_request_at: float | None = None
        self._page_requests = 0
        self.robot_parser: RobotFileParser | None = None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is not None:
            wait = self.min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _get(self, url: str, *, count_page: bool) -> httpx.Response:
        if not is_same_domain(url):
            raise ValueError(f"Refusing off-domain URL: {url}")
        if count_page and self._page_requests >= self.max_pages:
            raise RuntimeError(f"Scraper page cap ({self.max_pages}) reached")
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            self._wait_for_rate_limit()
            if count_page:
                if self._page_requests >= self.max_pages:
                    raise RuntimeError(f"Scraper page cap ({self.max_pages}) reached")
                self._page_requests += 1
            try:
                response = self.client.get(url, headers={"User-Agent": self.settings.user_agent})
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    redirected = httpx.URL(url).join(location)
                    if redirected.host != "iit.tn":
                        raise ValueError("Refusing an off-domain redirect")
                    self._wait_for_rate_limit()
                    if count_page:
                        if self._page_requests >= self.max_pages:
                            raise RuntimeError(f"Scraper page cap ({self.max_pages}) reached")
                        self._page_requests += 1
                    response = self.client.get(str(redirected), headers={"User-Agent": self.settings.user_agent})
                response.raise_for_status()
                if urlparse(str(response.url)).hostname != "iit.tn":
                    raise ValueError("Refusing an off-domain response")
                return response
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == MAX_RETRIES:
                    break
                time.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
        raise RuntimeError(f"Could not fetch {url}: {last_error}") from last_error

    def check_robots(self) -> RobotFileParser:
        response = self._get(ROBOTS_URL, count_page=False)
        parser = RobotFileParser()
        parser.set_url(ROBOTS_URL)
        parser.parse(response.text.splitlines())
        self.robot_parser = parser
        return parser

    def allowed_seed_pages(self) -> tuple[list, list]:
        parser = self.robot_parser or self.check_robots()
        allowed, disallowed = [], []
        for page in SEED_PAGES:
            (allowed if parser.can_fetch(self.settings.user_agent, page.url) else disallowed).append(page)
        return allowed, disallowed

    @staticmethod
    def _cache_stem(url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return digest

    def _cache_paths(self, url: str, is_pdf: bool) -> tuple[Path, Path]:
        stem = self._cache_stem(url)
        return self.cache_dir / f"{stem}.{'txt' if is_pdf else 'html'}", self.cache_dir / f"{stem}.meta.json"

    def _read_cached(self, url: str, is_pdf: bool) -> FetchedDocument | None:
        content_path, metadata_path = self._cache_paths(url, is_pdf)
        if not content_path.exists() or not metadata_path.exists():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("url") != url or metadata.get("sanitizer_version") != SANITIZER_VERSION:
                return None
            return FetchedDocument(
                url=url,
                content=content_path.read_text(encoding="utf-8"),
                content_hash=metadata["content_hash"],
                consulted_on=metadata["consulted_on"],
                content_type=metadata["content_type"],
                cached=True,
            )
        except (OSError, KeyError, json.JSONDecodeError):
            return None

    def fetch_page(self, page) -> FetchedDocument:
        if page not in SEED_PAGES:
            raise ValueError("Only explicitly allowlisted seed pages may be fetched")
        if self.robot_parser is None:
            self.check_robots()
        if not self.robot_parser.can_fetch(self.settings.user_agent, page.url):
            raise PermissionError(f"robots.txt disallows {page.url}")
        is_pdf = page.url.lower().endswith(".pdf")
        cached = self._read_cached(page.url, is_pdf)
        if cached:
            return cached
        response = self._get(page.url, count_page=True)
        raw = response.content
        content_hash = hashlib.sha256(raw).hexdigest()
        content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
        consulted_on = date.today().isoformat()
        if is_pdf or content_type == "application/pdf":
            reader = PdfReader(BytesIO(raw))
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
            safe_content = sanitize_pdf_text(extracted)
        else:
            safe_content = sanitize_html(raw.decode(response.encoding or "utf-8", "replace"), page.url)
        content_path, metadata_path = self._cache_paths(page.url, is_pdf)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        content_path.write_text(safe_content, encoding="utf-8", newline="\n")
        metadata_path.write_text(
            json.dumps(
                {
                    "url": page.url,
                    "content_hash": content_hash,
                    "consulted_on": consulted_on,
                    "content_type": content_type,
                    "sanitized_cache": True,
                    "sanitizer_version": SANITIZER_VERSION,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return FetchedDocument(page.url, safe_content, content_hash, consulted_on, content_type, False)
