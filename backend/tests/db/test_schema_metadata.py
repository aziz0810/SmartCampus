from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint

from app.models import Base, Program, ProgramSubject, TuitionFee


def test_all_tables_have_primary_keys_and_foreign_keys_are_indexed_and_explicit():
    for table in Base.metadata.tables.values():
        assert table.primary_key.columns, f"{table.name} has no primary key"
        for foreign_key in table.foreign_key_constraints:
            assert foreign_key.ondelete in {"RESTRICT", "CASCADE", "SET NULL"}, (
                f"{table.name} has an FK without explicit ON DELETE"
            )
            for column in foreign_key.columns:
                covered = any(
                    list(index.columns)[0].name == column.name
                    for index in table.indexes
                    if index.columns
                )
                covered = covered or any(
                    isinstance(constraint, (PrimaryKeyConstraint, UniqueConstraint))
                    and constraint.columns
                    and list(constraint.columns)[0].name == column.name
                    for constraint in table.constraints
                )
                assert covered, f"FK {table.name}.{column.name} has no leading index"


def test_positive_and_nonnegative_check_columns_are_required():
    assert Program.__table__.c.duration_semesters.nullable is False
    assert ProgramSubject.__table__.c.semester.nullable is False
    assert ProgramSubject.__table__.c.credits.nullable is False
    assert TuitionFee.__table__.c.amount.nullable is False


def test_value_range_checks_remain_in_metadata():
    constraints = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_program_duration_positive" in constraints
    assert "ck_program_subject_semester_positive" in constraints
    assert "ck_program_subject_credits_non_negative" in constraints
    assert "ck_tuition_fee_amount_non_negative" in constraints
    assert "ck_formation_kind_non_empty" in constraints
    assert "ck_tuition_fee_fee_type_non_empty" in constraints
