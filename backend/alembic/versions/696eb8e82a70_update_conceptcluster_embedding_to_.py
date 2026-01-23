"""Update ConceptCluster embedding to LargeBinary, add confidence default, and use timezone-aware datetime defaults

Revision ID: 696eb8e82a70
Revises: e1a5660c71c5
Create Date: 2026-01-23 16:25:11.335784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '696eb8e82a70'
down_revision: Union[str, Sequence[str], None] = 'e1a5660c71c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop and recreate concept_clusters table (data loss!)
    op.drop_table('concept_clusters')
    op.create_table(
        'concept_clusters',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subject', sa.String, nullable=False),
        sa.Column('embedding', sa.LargeBinary, nullable=False),
        sa.Column('name', sa.String, nullable=True),
        sa.Column('confidence', sa.String, nullable=False, server_default="Weak"),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('concept_clusters')
    op.create_table(
        'concept_clusters',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subject', sa.String, nullable=False),
        sa.Column('embedding', sa.String, nullable=False),
        sa.Column('name', sa.String, nullable=True),
        sa.Column('confidence', sa.String, nullable=False, server_default="Weak"),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
    )
