"""Initial schema — all §5.1 tables, created from the live model metadata.

Deliberately metadata-driven for the first revision: models are the source of
truth at bootstrap; subsequent revisions must be explicit op.* migrations.

Revision ID: 0001
Revises:
Create Date: 2026-07-03
"""
from alembic import op

from api.db import Base
import api.models  # noqa: F401 — populate metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
