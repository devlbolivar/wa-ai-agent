"""add_spanish_knowledge_categories

Revision ID: 34fadac77579
Revises: 6ed7d3301b8a
Create Date: 2026-02-28 08:10:03.922186

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34fadac77579'
down_revision: Union[str, Sequence[str], None] = '6ed7d3301b8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE knowledgecategoryenum ADD VALUE IF NOT EXISTS 'servicios';")
        op.execute("ALTER TYPE knowledgecategoryenum ADD VALUE IF NOT EXISTS 'horarios';")
        op.execute("ALTER TYPE knowledgecategoryenum ADD VALUE IF NOT EXISTS 'equipo';")
        op.execute("ALTER TYPE knowledgecategoryenum ADD VALUE IF NOT EXISTS 'ubicacion';")
        op.execute("ALTER TYPE knowledgecategoryenum ADD VALUE IF NOT EXISTS 'politicas';")


def downgrade() -> None:
    """Downgrade schema."""
    pass
