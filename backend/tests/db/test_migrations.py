from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import inspect

from app.models import Base


def test_upgrade_downgrade_base_upgrade_cycle(migrated_schema):
    connection, config = migrated_schema
    expected_tables = set(Base.metadata.tables)

    assert expected_tables.issubset(set(inspect(connection).get_table_names()))
    command.downgrade(config, "base")
    remaining_tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
    assert remaining_tables == set()

    command.upgrade(config, "head")
    assert expected_tables.issubset(set(inspect(connection).get_table_names()))


def test_alembic_metadata_drift_is_empty(migrated_schema):
    connection, _ = migrated_schema
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    differences = compare_metadata(context, Base.metadata)
    assert differences == []
