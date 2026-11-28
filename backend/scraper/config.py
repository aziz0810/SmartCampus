from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
ENV_FILE = REPO_ROOT / ".env"
SANITIZED_CACHE_DIR = BACKEND_ROOT / "scraper" / "output" / "cache"
CATALOG_OUTPUT = BACKEND_ROOT / "seed" / "iit_scraped_catalog.json"
COVERAGE_OUTPUT = BACKEND_ROOT / "scraper" / "output" / "coverage.md"

BASE_URL = "https://iit.tn"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
MAX_PAGES = 40
REQUEST_TIMEOUT_SECONDS = 15
MIN_REQUEST_INTERVAL_SECONDS = 2.0
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2.0


@dataclass(frozen=True)
class SeedPage:
    url: str
    page_type: str
    formation_kind: str | None = None
    formation_code: str | None = None
    optional: bool = False


SEED_PAGES = (
    SeedPage(f"{BASE_URL}/prepa/", "formation", "prepa", "prepa"),
    SeedPage(f"{BASE_URL}/architecture-2/", "formation", "architecture", "architecture"),
    SeedPage(f"{BASE_URL}/licences/", "index"),
    SeedPage(
        f"{BASE_URL}/licence-en-systemes-electriques-intelligents-energies-renouvelables/",
        "formation", "licence", "lic-sys-elec",
    ),
    SeedPage(f"{BASE_URL}/licence-en-mecatronique-systemes-intelligents/", "formation", "licence", "lic-mecatronique"),
    SeedPage(f"{BASE_URL}/reseaux-et-cybersecurite/", "formation", "licence", "res-cyber"),
    SeedPage(f"{BASE_URL}/systemes-embarques-internet-des-objets-iot/", "formation", "licence", "lic-iot"),
    SeedPage(f"{BASE_URL}/big-data-et-analyse-de-donnees/", "formation", "licence", "lic-big-data"),
    SeedPage(f"{BASE_URL}/genie-logiciel-systemes-intelligents/", "formation", "licence", "lic-info"),
    SeedPage(f"{BASE_URL}/mastere/", "index"),
    SeedPage(f"{BASE_URL}/filieres-ingenieur/", "index"),
    SeedPage(f"{BASE_URL}/filieres-ingenieur/genie-civil/", "formation", "ingenieur", "ing-genie-civil"),
    SeedPage(f"{BASE_URL}/genie-des-procedes/", "formation", "ingenieur", "ing-genie-procedes"),
    SeedPage(f"{BASE_URL}/filieres-ingenieur/genie-informatique-2/", "formation", "ingenieur", "ing-info"),
    SeedPage(f"{BASE_URL}/filieres-ingenieur/genie-mecanique-2/", "formation", "ingenieur", "ing-genie-mecanique"),
    SeedPage(f"{BASE_URL}/filieres-ingenieur/genie-industriel-2/", "formation", "ingenieur", "ing-genie-industriel"),
    SeedPage(f"{BASE_URL}/formation-continue/", "formation", "formation_continue", "formation-continue"),
    SeedPage(f"{BASE_URL}/test/procedure-et-frais-dinscription/", "admission"),
    SeedPage(f"{BASE_URL}/test/bourse/", "admission"),
    SeedPage(
        f"{BASE_URL}/wp-content/uploads/2026/10/Criteres_d_admission.pdf",
        "admission_pdf", optional=True,
    ),
)


class ScraperSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    scraper_contact_email: str

    @field_validator("scraper_contact_email")
    @classmethod
    def validate_contact_email(cls, value: str) -> str:
        value = value.strip()
        local, separator, domain = value.partition("@")
        if not separator or not local or "." not in domain or any(c.isspace() for c in value):
            raise ValueError("SCRAPER_CONTACT_EMAIL must be a project contact email")
        return value

    @property
    def user_agent(self) -> str:
        return f"SmartCampusAI-student-project/0.1 (contact: {self.scraper_contact_email})"


def is_same_domain(url: str) -> bool:
    return urlparse(url).scheme == "https" and urlparse(url).hostname == "iit.tn"
