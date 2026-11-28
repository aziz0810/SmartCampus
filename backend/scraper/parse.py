from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from scraper.config import SeedPage
from scraper.fetch import FetchedDocument, sanitize_text

ACADEMIC_SECTION_RE = re.compile(
    r"admission|prérequis|condition|débouch|carrière|programme|cursus|semestre|matière|durée|diplôme|spécialit|option",
    re.I,
)
ADMISSION_RE = re.compile(r"admission|condition d'accès|prérequis", re.I)
CAREER_RE = re.compile(r"débouch|carrière|opportunités professionnelles", re.I)
SPECIALTY_RE = re.compile(r"spécialit|option|parcours", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\s*[-/–]\s*(20\d{2})\b")
DURATION_RE = re.compile(r"\b(\d+)\s*(semestre|semestres|année|années|an|ans)\b", re.I)
CREDIT_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:crédit|crédits|ECTS)\b", re.I)
SEMESTER_RE = re.compile(r"\b(?:semestre|semester|S)\s*([1-9]\d?)\b", re.I)
FEE_AMOUNT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:TND|DT|EUR|€|dinars?)\b", re.I)


@dataclass
class PageResult:
    formations: list[dict] = field(default_factory=list)
    subjects: list[dict] = field(default_factory=list)
    programs: list[dict] = field(default_factory=list)
    tuition_fees: list[dict] = field(default_factory=list)
    admission_notes: list[dict] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)


def slug_code(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:50] or "general"


def provenance(document: FetchedDocument) -> dict[str, str | bool]:
    return {
        "source_url": document.url,
        "consulted_on": document.consulted_on,
        "content_hash": document.content_hash,
        "needs_review": True,
    }


def source_note(document: FetchedDocument) -> str:
    return f"Source: {document.url}; consulted {document.consulted_on}"


def _content_sections(soup: BeautifulSoup) -> list[Tag]:
    selectors = ".bt_bb_section, .elementor-section"
    sections = list(soup.select(selectors))
    if sections:
        return sections
    body = soup.body
    return [body] if body else []


def _section_heading(section: Tag) -> str | None:
    for heading in section.select(
        "h1, h2, h3, h4, h5, h6, .bt_bb_headline_content, .elementor-heading-title"
    ):
        value = sanitize_text(heading.get_text(" ", strip=True))
        if value:
            return value
    return None


def _academic_text(section: Tag) -> str:
    parts = []
    for block in section.select(".bt_bb_text, .elementor-widget-text-editor, p, li"):
        text = sanitize_text(block.get_text(" ", strip=True))
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts)


def _first_title(soup: BeautifulSoup) -> str | None:
    for heading in soup.select(
        ".bt_bb_section h1, .bt_bb_section h2, .bt_bb_section h3, "
        ".elementor-section h1, .elementor-section h2, .elementor-section h3, "
        ".bt_bb_headline_content, .elementor-heading-title"
    ):
        value = sanitize_text(heading.get_text(" ", strip=True))
        if value and not re.search(r"organisation du diplôme|nos formations|voir nos formations", value, re.I):
            return value
    if soup.title:
        value = sanitize_text(soup.title.get_text(" ", strip=True))
        value = re.split(r"\s*(?:\||\u2013|\u2014)\s*", value, maxsplit=1)[0].strip()
        if value and not re.search(r"page not found|404", value, re.I):
            return value
    return None


def _first_description(soup: BeautifulSoup) -> str | None:
    for block in soup.select(".bt_bb_text p, .elementor-widget-text-editor p, .bt_bb_text, .elementor-widget-text-editor"):
        value = sanitize_text(block.get_text(" ", strip=True))
        if value and len(value) >= 40 and not ACADEMIC_SECTION_RE.search(value):
            return value
    return None


def _duration_semesters(text: str) -> int | None:
    match = DURATION_RE.search(text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("semestre"):
        return amount
    # Two semesters per explicitly stated academic year; the published value
    # is converted to the model's semester unit, not inferred from a pathway.
    if unit in {"année", "années", "an", "ans"}:
        return amount * 2
    return None


def _year(text: str) -> str | None:
    match = YEAR_RE.search(text)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _specialties(soup: BeautifulSoup, source: FetchedDocument) -> list[dict]:
    result = []
    for section in _content_sections(soup):
        heading = _section_heading(section) or ""
        if not SPECIALTY_RE.search(heading):
            continue
        for subheading in section.find_all(["h3", "h4", "h5", "h6"]):
            name = sanitize_text(subheading.get_text(" ", strip=True))
            if name and name.lower() != heading.lower():
                result.append({
                    "code": slug_code(name),
                    "name": name,
                    "description": None,
                    "is_demo": False,
                    "needs_review": True,
                    "source_note": source_note(source),
                    "provenance": provenance(source),
                })
    if not result:
        result.append({
            "code": "general",
            "name": "general",
            "description": None,
            "is_demo": False,
            "needs_review": True,
            "source_note": source_note(source),
            "provenance": provenance(source),
        })
    return result


def _curriculum(soup: BeautifulSoup, page: SeedPage, document: FetchedDocument) -> tuple[list[dict], list[dict], int | None, str | None]:
    subjects_by_code: dict[str, dict] = {}
    program_subjects = []
    full_text = "\n".join(_academic_text(section) for section in _content_sections(soup))
    academic_year = _year(full_text)
    duration = _duration_semesters(full_text)

    for section in _content_sections(soup):
        current_semester = None
        for node in section.select(
            "h2, h3, h4, h5, p, li, tr, .bt_bb_headline_content, .elementor-heading-title"
        ):
            text = sanitize_text(node.get_text(" ", strip=True))
            semester_match = SEMESTER_RE.search(text)
            if semester_match:
                current_semester = int(semester_match.group(1))
                if node.name in {"h2", "h3", "h4", "h5"} or "bt_bb_headline_content" in node.get("class", []) or "elementor-heading-title" in node.get("class", []):
                    continue
            if node.name == "tr":
                cells = [sanitize_text(cell.get_text(" ", strip=True)) for cell in node.find_all(["th", "td"])]
                if len(cells) < 2 or any(re.search(r"Erasmus|GPA|candidate|nom complet", cell, re.I) for cell in cells):
                    continue
                subject_name = cells[0]
                credit_match = next((CREDIT_RE.search(cell) for cell in cells[1:] if CREDIT_RE.search(cell)), None)
                if credit_match:
                    credits = float(credit_match.group(1).replace(",", "."))
                else:
                    numeric = next((re.fullmatch(r"\d+(?:[.,]\d+)?", cell) for cell in cells[1:] if re.fullmatch(r"\d+(?:[.,]\d+)?", cell)), None)
                    credits = float(numeric.group(0).replace(",", ".")) if numeric else None
            elif node.name in {"li", "p"}:
                if current_semester is None or not text or len(text) > 180:
                    continue
                credit_match = CREDIT_RE.search(text)
                if credit_match:
                    credits = float(credit_match.group(1).replace(",", "."))
                    subject_name = CREDIT_RE.sub("", text).strip(" -–:;,.\t")
                else:
                    continue
            else:
                continue
            if not subject_name or len(subject_name) > 120:
                continue
            code = slug_code(subject_name)
            subject = subjects_by_code.setdefault(code, {
                "code": code,
                "name": subject_name,
                "description": None,
                "is_demo": False,
                "needs_review": True,
                "source_note": source_note(document),
                "provenance": provenance(document),
            })
            program_subjects.append({
                "subject_code": subject["code"],
                "semester": current_semester,
                "credits": credits,
                "is_optional": False,
                "is_demo": False,
                "needs_review": True,
                "source_note": source_note(document),
                "provenance": provenance(document),
            })

    subjects = list(subjects_by_code.values())
    programs = []
    if academic_year:
        duration_value = duration
        programs.append({
            "formation_code": page.formation_code,
            "specialty_code": "general",
            "academic_year": academic_year,
            "duration_semesters": duration_value,
            "description": None,
            "subjects": program_subjects,
            "is_demo": False,
            "needs_review": True,
            "source_note": source_note(document),
            "provenance": provenance(document),
        })
    return subjects, programs, duration, academic_year


def parse_formation(page: SeedPage, document: FetchedDocument) -> PageResult:
    soup = BeautifulSoup(document.content, "lxml")
    title = _first_title(soup)
    description = _first_description(soup)
    text = "\n".join(_academic_text(section) for section in _content_sections(soup))
    subjects, programs, duration, academic_year = _curriculum(soup, page, document)
    specialties = _specialties(soup, document)
    formation = {
        "code": page.formation_code,
        "institution_code": "iit",
        "name": title,
        "kind": page.formation_kind,
        "description": description,
        "specialties": specialties,
        "is_demo": False,
        "needs_review": True,
        "source_note": source_note(document),
        "provenance": provenance(document),
    }
    found = ["kind", "specialties"]
    missing = []
    (found if title else missing).append("name")
    for field_name, value in (("description", description), ("duration", duration), ("curriculum", subjects), ("academic_year", academic_year)):
        (found if value is not None and value != [] else missing).append(field_name)
    heading_text = " ".join(
        sanitize_text(heading.get_text(" ", strip=True))
        for heading in soup.select(
            ".bt_bb_section h1, .bt_bb_section h2, .bt_bb_section h3, .bt_bb_section h4, "
            ".elementor-section h1, .elementor-section h2, .elementor-section h3, .elementor-section h4, "
            ".bt_bb_headline_content, .elementor-heading-title"
        )
    )
    notes = []
    for label, pattern in (("admission conditions", ADMISSION_RE), ("career opportunities", CAREER_RE)):
        if pattern.search(heading_text):
            found.append(label)
            notes.append(f"{label.capitalize()} are present on the page but are not represented by the current relational model.")
        else:
            missing.append(label)
    if FEE_AMOUNT_RE.search(text):
        found.append("public fee amount text")
        missing.append("structured tuition_fee")
        notes.append(
            "A public fee amount was mentioned, but no tuition_fee row was emitted because the source does not provide the model's required academic year and fee type together."
        )
    else:
        missing.append("public fee amount")
    if not title:
        notes.append("No formation title was found; this page will not produce a database row.")
    result = PageResult(
        formations=[formation] if title else [],
        subjects=subjects,
        programs=programs,
        coverage={"url": document.url, "consulted_on": document.consulted_on, "found": found, "missing": missing, "notes": notes},
    )
    return result


def parse_index(page: SeedPage, document: FetchedDocument, allowlisted_urls: set[str]) -> PageResult:
    soup = BeautifulSoup(document.content, "lxml")
    links = []
    for anchor in soup.select(".bt_bb_section a[href], .elementor-section a[href]"):
        url = urljoin(document.url, str(anchor.get("href", "")).split("#", 1)[0]).rstrip("/") + "/"
        if url in allowlisted_urls and url not in links:
            links.append(url)
    headings = [sanitize_text(h.get_text(" ", strip=True)) for h in soup.select(".bt_bb_section h1, .bt_bb_section h2, .bt_bb_section h3, .elementor-section h1, .elementor-section h2, .elementor-section h3, .elementor-section h4")]
    return PageResult(coverage={
        "url": document.url,
        "consulted_on": document.consulted_on,
        "found": ["page headings", "allowlisted formation links"],
        "missing": ["formation details on index page"],
        "notes": [
            f"Observed allowlisted links: {', '.join(links) if links else 'none'}; no links were followed.",
            f"Observed {len(headings)} headings.",
        ],
    })


def parse_admission(page: SeedPage, document: FetchedDocument) -> PageResult:
    if page.page_type == "admission_pdf":
        text = document.content
    else:
        soup = BeautifulSoup(document.content, "lxml")
        text = "\n".join(_academic_text(section) for section in _content_sections(soup))
    found = []
    if re.search(r"admission|inscription|candidat|dossier|bourse|critère|condition", text, re.I):
        found.append("admission criteria text")
    if re.search(r"\b\d+(?:[,.]\d+)?\s*(?:TND|DT|dinar(?:s)?)\b", text, re.I):
        found.append("fee amount text (requires manual review; never includes bank details)")
        fee_note = "A fee amount is mentioned, but no tuition_fee row was emitted without an explicit academic year and fee type."
    else:
        fee_note = "No fee amount was found."
    return PageResult(
        admission_notes=[],
        coverage={
            "url": document.url,
            "consulted_on": document.consulted_on,
            "found": found,
            "missing": ["admission-condition database field", "fee amount"],
            "notes": ["Admission text is reported in coverage only because the current relational model has no admission field.", fee_note],
        },
    )
