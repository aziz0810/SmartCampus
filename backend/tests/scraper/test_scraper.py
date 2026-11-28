from pathlib import Path

import httpx
import pytest

from scraper.config import SEED_PAGES, ScraperSettings
from scraper.export import _assert_safe, build_catalog
from scraper.fetch import FetchedDocument, PoliteFetcher, sanitize_html
from scraper.parse import parse_formation, parse_index

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = FetchedDocument(
    url=SEED_PAGES[13].url,
    content_hash="a" * 64,
    consulted_on="2026-11-26",
    content_type="text/html",
    cached=False,
    content="",
)


def test_parse_btbb_formation_fixture():
    page = SEED_PAGES[13]
    document = FetchedDocument(
        **{**SOURCE.__dict__, "content": (FIXTURES / "btbb_formation.html").read_text(encoding="utf-8")}
    )
    result = parse_formation(page, document)

    assert result.formations[0]["name"] == "Génie Informatique"
    assert result.formations[0]["kind"] == "ingenieur"
    assert result.formations[0]["provenance"]["source_url"] == page.url
    assert result.coverage["found"] == ["kind", "specialties", "name", "duration"]
    assert result.coverage["missing"] == [
        "description", "curriculum", "academic_year", "admission conditions", "career opportunities", "public fee amount"
    ]


def test_parse_formation_uses_page_title_when_site_has_no_heading_tags():
    page = SEED_PAGES[13]
    result = parse_formation(page, FetchedDocument(
        url=page.url,
        content="<html><head><title>Génie Informatique | IIT</title></head><body><h4>MP1</h4></body></html>",
        content_hash="c" * 64,
        consulted_on="2026-11-26",
        content_type="text/html",
        cached=True,
    ))
    assert result.formations[0]["name"] == "Génie Informatique"


def test_parse_elementor_index_only_recognizes_allowlisted_links():
    page = SEED_PAGES[2]
    document = FetchedDocument(
        **{**SOURCE.__dict__, "url": page.url, "content": (FIXTURES / "elementor_index.html").read_text(encoding="utf-8")}
    )
    result = parse_index(page, document, {entry.url for entry in SEED_PAGES})
    assert "allowlisted formation links" in result.coverage["found"]
    assert "https://iit.tn/reseaux-et-cybersecurite/" in result.coverage["notes"][0]
    assert "external.example" not in str(result.coverage)


def test_sanitizer_removes_contacts_portals_bank_data_and_news():
    html = """<html><body><section class='bt_bb_section'><p>Admission du dossier</p>
    <p>Contact person@example.invalid +216 22 345 678</p><a href='mailto:someone@example.invalid'>Mail</a>
    <a href='/login/'>Connexion</a><p>IBAN TN000000000000</p></section>
    <section class='news'><h2>Actualités</h2><p>News body</p></section></body></html>"""
    cleaned = sanitize_html(html, "https://iit.tn/test/procedure-et-frais-dinscription/")
    assert "Admission du dossier" in cleaned
    assert "@" not in cleaned
    assert "22 345 678" not in cleaned
    assert "IBAN" not in cleaned
    assert "News body" not in cleaned
    assert "Connexion" not in cleaned


def test_sanitizer_drops_entire_fee_table_with_bank_account_number():
    html = """<table><tr><th>Frais d'inscription</th><td>1200 TND</td></tr>
    <tr><th>RIB</th><td>TN59 1000 0000 0000 0000 0000</td></tr></table>"""
    cleaned = sanitize_html(html, "https://iit.tn/test/procedure-et-frais-dinscription/")
    assert "TN59" not in cleaned
    assert "1200 TND" not in cleaned


def test_sanitizer_keeps_page_body_when_its_class_has_sensitive_word():
    html = """<html><body class='news-template'>
    <section class='bt_bb_section'><h2>Formation</h2><p>Programme public.</p></section>
    </body></html>"""
    cleaned = sanitize_html(html, "https://iit.tn/prepa/")
    assert "Formation" in cleaned
    assert "Programme public." in cleaned


def test_export_rejects_personal_contact_and_bank_markers():
    with pytest.raises(ValueError, match="Email-like"):
        _assert_safe({"description": "Email hidden@example.invalid"})
    with pytest.raises(ValueError, match="Bank-detail"):
        _assert_safe({"description": "IBAN value"})
    _assert_safe({"provenance": {"content_hash": "12345678"}})


def test_catalog_provenance_shape_and_model_sections():
    page = SEED_PAGES[13]
    result = parse_formation(page, FetchedDocument(
        url=page.url,
        content=(FIXTURES / "btbb_formation.html").read_text(encoding="utf-8"),
        content_hash="b" * 64,
        consulted_on="2026-11-26",
        content_type="text/html",
        cached=True,
    ))
    catalog = build_catalog([result], "2026-11-26")
    assert set(catalog) == {"meta", "institutions", "formations", "subjects", "programs", "tuition_fees"}
    row = catalog["formations"][0]
    assert row["is_demo"] is False and row["needs_review"] is True
    assert row["provenance"]["content_hash"] == "b" * 64


def test_fetcher_checks_robots_and_uses_cache(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><section class='bt_bb_section'><p>Course details</p></section></body></html>",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = PoliteFetcher(
        ScraperSettings(scraper_contact_email="team@example.org"),
        cache_dir=tmp_path,
        client=client,
        min_interval=0,
    )
    try:
        fetcher.check_robots()
        first = fetcher.fetch_page(SEED_PAGES[0])
        second = fetcher.fetch_page(SEED_PAGES[0])
    finally:
        fetcher.close()

    assert len(requests) == 2
    assert all(request.headers["user-agent"].startswith("SmartCampusAI-student-project/0.1") for request in requests)
    assert first.cached is False
    assert second.cached is True
    assert first.content_hash == second.content_hash


def test_page_cap_counts_failed_http_attempts(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = PoliteFetcher(
        ScraperSettings(scraper_contact_email="team@example.org"),
        cache_dir=tmp_path,
        client=client,
        min_interval=0,
        max_pages=1,
    )
    try:
        with pytest.raises(RuntimeError, match="page cap"):
            fetcher._get(SEED_PAGES[0].url, count_page=True)
    finally:
        fetcher.close()

    assert len(requests) == 1
