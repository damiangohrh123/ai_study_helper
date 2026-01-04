"""Remove session_id column from users table

Revision ID: 1a2b3c4d5e6f
Revises: 0d20e181f308
Create Date: 2026-01-04
"""

# Alembic revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = '0d20e181f308'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.drop_column('users', 'session_id')

def downgrade():
    op.add_column('users', sa.Column('session_id', sa.String(), unique=True, index=True, nullable=True))