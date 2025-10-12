"""Initial schema bootstrap."""

from __future__ import annotations

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251012_0001"
down_revision = None
branch_labels = None
depends_on = None


def _load_schema_sql() -> str:
    schema_path = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")


def upgrade() -> None:
    """Apply the initial SQL schema."""

    op.execute(_load_schema_sql())


def downgrade() -> None:
    """Drop all objects created by :func:`upgrade`."""

    op.execute(
        """
        SET FOREIGN_KEY_CHECKS = 0;
        DROP TABLE IF EXISTS track_candidate;
        DROP TABLE IF EXISTS rating;
        DROP TABLE IF EXISTS listen;
        DROP TABLE IF EXISTS track_genre;
        DROP TABLE IF EXISTS track_artist;
        DROP TABLE IF EXISTS track;
        DROP TABLE IF EXISTS album;
        DROP TABLE IF EXISTS label;
        DROP TABLE IF EXISTS genre;
        DROP TABLE IF EXISTS artist_alias;
        DROP TABLE IF EXISTS artist;
        DROP TABLE IF EXISTS user_account;
        SET FOREIGN_KEY_CHECKS = 1;
        """
    )
