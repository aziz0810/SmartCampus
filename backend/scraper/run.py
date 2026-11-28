from __future__ import annotations

from datetime import date
import re

from scraper.config import BASE_URL, CATALOG_OUTPUT, COVERAGE_OUTPUT, SEED_PAGES, SeedPage, ScraperSettings
from scraper.export import build_catalog, write_outputs
from scraper.fetch import PoliteFetcher
from scraper.parse import PageResult, parse_admission, parse_formation, parse_index, slug_code

FORMATION_TITLE_RE = re.compile(
    r"cycle|licence|master|architecture|pr[eé]pa|ing[eé]nieur|formation continue|[eé]cole|bachelor|doctorat",
    re.I,
)


def scrape() -> tuple[dict, list[dict]]:
    settings = ScraperSettings()
    known_pages = {page.url: page for page in SEED_PAGES}
    root = known_pages.get(BASE_URL + "/", SeedPage(BASE_URL + "/", "index"))
    queue = [root]
    queued = {root.url}
    visited: set[str] = set()
    results: list[PageResult] = []
    coverage: list[dict] = []
    fetcher = PoliteFetcher(settings)
    try:
        fetcher.check_robots()
        # Breadth-first discovery begins at BASE_URL and follows crawlable links
        # on the same HTTPS host until the fetcher's page cap is reached.
        while queue:
            page = queue.pop(0)
            if page.url in visited:
                continue
            visited.add(page.url)
            try:
                document = fetcher.fetch_page(page)
            except Exception as exc:  # Keep coverage complete without exposing response bodies.
                coverage.append({
                    "url": page.url,
                    "found": [],
                    "missing": ["all requested fields"],
                    "notes": [f"Fetch or parse input unavailable ({type(exc).__name__}); no value was inferred."],
                })
                continue
            for url in fetcher.discover_links(document):
                if url in visited or url in queued:
                    continue
                discovered = known_pages.get(url)
                if discovered is None:
                    if url.lower().endswith(".pdf"):
                        discovered = SeedPage(url, "admission_pdf", optional=True)
                    else:
                        discovered = SeedPage(url, "formation", "other", slug_code(url.rstrip("/").rsplit("/", 1)[-1]))
                queue.append(discovered)
                queued.add(url)
            allowlist = visited | queued
            if page.page_type == "formation":
                result = parse_formation(page, document)
                if page.url not in known_pages and result.formations:
                    title = result.formations[0].get("name") or ""
                    if not FORMATION_TITLE_RE.search(title):
                        result.formations.clear()
                        result.subjects.clear()
                        result.programs.clear()
                        result.coverage.setdefault("notes", []).append(
                            "Page was crawled, but its title did not identify a formation; no catalog row was emitted."
                        )
            elif page.page_type == "index":
                result = parse_index(page, document, allowlist)
            else:
                result = parse_admission(page, document)
            if not document.content.strip():
                result.coverage.setdefault("notes", []).append(
                    "No static text remained after privacy filtering; JavaScript rendering is disabled."
                )
            results.append(result)
            coverage.append(result.coverage)
            if len(visited) >= fetcher.max_pages and queue:
                coverage.append({
                    "url": "(crawl limit)",
                    "found": [],
                    "missing": [],
                    "notes": [f"Stopped after the configured {fetcher.max_pages}-page limit; {len(queue)} discovered URLs were left unrequested."],
                })
                break
    finally:
        fetcher.close()

    consulted_dates = [row.get("consulted_on") for row in coverage if row.get("consulted_on")]
    consulted_on = max(consulted_dates, default=date.today().isoformat())
    catalog = build_catalog(results, consulted_on)
    return catalog, coverage


def main() -> None:
    catalog, coverage = scrape()
    write_outputs(catalog, coverage)
    print(f"Wrote {CATALOG_OUTPUT}")
    print(f"Wrote {COVERAGE_OUTPUT}")
    print(
        f"Catalog counts: {len(catalog['formations'])} formations, "
        f"{len(catalog['subjects'])} subjects, {len(catalog['programs'])} programs, "
        f"{len(catalog['tuition_fees'])} tuition fees; {len(coverage)} pages reported."
    )


if __name__ == "__main__":
    main()
