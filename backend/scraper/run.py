from __future__ import annotations

from datetime import date

from scraper.config import CATALOG_OUTPUT, COVERAGE_OUTPUT, SEED_PAGES, ScraperSettings
from scraper.export import build_catalog, write_outputs
from scraper.fetch import PoliteFetcher
from scraper.parse import PageResult, parse_admission, parse_formation, parse_index


def scrape() -> tuple[dict, list[dict]]:
    settings = ScraperSettings()
    allowlist = {page.url for page in SEED_PAGES}
    results: list[PageResult] = []
    coverage: list[dict] = []
    fetcher = PoliteFetcher(settings)
    try:
        fetcher.check_robots()
        allowed, disallowed = fetcher.allowed_seed_pages()
        for page in disallowed:
            coverage.append({
                "url": page.url,
                "found": [],
                "missing": ["all requested fields"],
                "notes": ["Skipped because robots.txt disallows this URL."],
            })
        for page in allowed:
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
            if page.page_type == "formation":
                result = parse_formation(page, document)
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
