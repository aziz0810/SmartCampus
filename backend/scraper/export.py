from __future__ import annotations

import json
import re
from pathlib import Path

from scraper.config import CATALOG_OUTPUT, COVERAGE_OUTPUT
from scraper.parse import PageResult

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+216[ .]?)?(?:[2-9]\d{7}|[2-9]\d(?:[ .]\d{3}){2})(?!\d)")
BANK_RE = re.compile(r"\b(?:IBAN|SWIFT|BIC|RIB|bank account|compte bancaire|virement bancaire)\b", re.I)


def _assert_safe(value, path: str = "$", seen: set[str] | None = None) -> None:
    seen = seen or set()
    if isinstance(value, dict):
        for key, child in value.items():
            # Hashes are machine identifiers, not user-facing text. Their hex
            # digits can coincidentally match the shape of an eight-digit phone.
            if key == "content_hash":
                continue
            _assert_safe(child, f"{path}.{key}", seen)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_safe(child, f"{path}[{index}]", seen)
    elif isinstance(value, str):
        if EMAIL_RE.search(value):
            raise ValueError(f"Email-like value found in catalog at {path}")
        if PHONE_RE.search(value):
            raise ValueError(f"Phone-like value found in catalog at {path}")
        if BANK_RE.search(value):
            raise ValueError(f"Bank-detail label found in catalog at {path}")


def build_catalog(results: list[PageResult], consulted_on: str) -> dict:
    formations_by_code: dict[str, dict] = {}
    subjects_by_code: dict[str, dict] = {}
    programs_by_key: dict[tuple, dict] = {}
    fees_by_key: dict[tuple, dict] = {}
    sources = []

    for result in results:
        if result.coverage.get("url"):
            sources.append(result.coverage["url"])
        for formation in result.formations:
            code = formation.get("code")
            if code:
                formations_by_code[code] = formation
        for subject in result.subjects:
            subjects_by_code[subject["code"]] = subject
        for program in result.programs:
            key = (program.get("formation_code"), program.get("specialty_code"), program.get("academic_year"))
            programs_by_key[key] = program
        for fee in result.tuition_fees:
            key = (fee.get("formation_code"), fee.get("academic_year"), fee.get("fee_type"))
            fees_by_key[key] = fee

    first_provenance = next(
        (formation.get("provenance") for formation in formations_by_code.values()),
        {"source_url": "https://iit.tn/", "consulted_on": consulted_on, "content_hash": None, "needs_review": True},
    )
    catalog = {
        "meta": {
            "catalog_name": "IIT scraped catalog",
            "consulted_on": consulted_on,
            "source_count": len(set(sources)),
            "needs_review": True,
            "notes": [
                "Scraped values are unverified and require human review.",
                "The current SQLAlchemy model has no admission-condition or career-opportunity columns; see coverage.md.",
                "Scraper-generated formation and subject codes are provisional and require reconciliation with the team's seed catalog before database loading.",
                "No program or tuition-fee rows are emitted unless the source provides the required academic year and fee type explicitly.",
            ],
        },
        "institutions": [
            {
                "code": "iit",
                "name": "IIT Sfax",
                "website_url": "https://iit.tn",
                "is_demo": False,
                "provenance": first_provenance,
            }
        ],
        "formations": sorted(formations_by_code.values(), key=lambda row: row["code"]),
        "subjects": sorted(subjects_by_code.values(), key=lambda row: row["code"]),
        "programs": [programs_by_key[key] for key in sorted(programs_by_key, key=lambda item: tuple(str(part or "") for part in item))],
        "tuition_fees": [fees_by_key[key] for key in sorted(fees_by_key, key=lambda item: tuple(str(part or "") for part in item))],
    }
    _assert_safe(catalog)
    return catalog


def write_outputs(catalog: dict, coverage: list[dict], catalog_path: Path = CATALOG_OUTPUT, coverage_path: Path = COVERAGE_OUTPUT) -> None:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# IIT scraper coverage",
        "",
        "Coverage lists pages discovered from BASE_URL and processed within the configured crawl limit. No values were inferred; missing values remain absent or null.",
        "",
        "| Page | Found | Missing | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for page in coverage:
        url = page.get("url", "(not fetched)")
        found = ", ".join(page.get("found", [])) or "—"
        missing = ", ".join(page.get("missing", [])) or "—"
        notes = "; ".join(page.get("notes", [])) or "—"
        lines.append(f"| [{url}]({url}) | {found} | {missing} | {notes} |")
    coverage_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
