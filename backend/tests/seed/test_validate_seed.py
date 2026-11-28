from copy import deepcopy
from pathlib import Path

import pytest

from seed.validate_seed import load_seed_file, validate_seed


SEED_PATH = Path(__file__).resolve().parents[2] / "seed" / "demo_catalog.json"


@pytest.fixture
def raw_seed() -> dict:
    import json

    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def test_curated_seed_validates_and_has_expected_provenance() -> None:
    seed = load_seed_file(SEED_PATH)
    assert len(seed.formations) == 15
    assert len(seed.program_subjects) == 40
    assert all("needs_review=true" in row.source_note for row in seed.formations if not row.is_demo)
    assert all(row.is_demo for row in seed.programs)
    assert all(row.is_demo for row in seed.tuition_fees)


def test_rejects_duplicate_subject_code(raw_seed: dict) -> None:
    data = deepcopy(raw_seed)
    data["subjects"].append(deepcopy(data["subjects"][0]))
    with pytest.raises(ValueError, match="duplicate subject code"):
        validate_seed(data)


def test_rejects_dangling_formation_reference(raw_seed: dict) -> None:
    data = deepcopy(raw_seed)
    data["formations"][0]["institution_code"] = "unknown"
    with pytest.raises(ValueError, match="unknown institution"):
        validate_seed(data)


def test_rejects_negative_fee(raw_seed: dict) -> None:
    data = deepcopy(raw_seed)
    data["tuition_fees"][0]["amount"] = "-1.00"
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        validate_seed(data)


def test_rejects_email_outside_reserved_domain(raw_seed: dict) -> None:
    data = deepcopy(raw_seed)
    data["app_users"][0]["email"] = "person@real-company.tn"
    with pytest.raises(ValueError, match="example.com"):
        validate_seed(data)


@pytest.mark.parametrize(
    "value, message",
    [
        ("IBAN TN5900000000000000000000", "bank account"),
        ("Call +216 20 123 456", "phone numbers"),
    ],
)
def test_rejects_sensitive_identifiers_in_text(raw_seed: dict, value: str, message: str) -> None:
    data = deepcopy(raw_seed)
    data["subjects"][0]["description"] = value
    with pytest.raises(ValueError, match=message):
        validate_seed(data)


def test_rejects_password_fields(raw_seed: dict) -> None:
    data = deepcopy(raw_seed)
    data["app_users"][0]["password"] = "should-not-be-in-seed"
    with pytest.raises(ValueError, match="sensitive field"):
        validate_seed(data)
