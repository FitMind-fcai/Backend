"""remove workout reminders and preferred hour fields

Revision ID: 8932b1417e6b
Revises: 001
Create Date: 2026-06-26 19:17:39.410582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8932b1417e6b'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('notification_preferences', 'workout_reminders_enabled')
    op.drop_column('notification_preferences', 'workout_reminder_hour')
    op.drop_column('notification_preferences', 'sleep_reminder_hour')
    op.drop_column('notification_preferences', 'coaching_daily_hour')


def downgrade() -> None:
    op.add_column('notification_preferences', sa.Column('coaching_daily_hour', sa.INTEGER(), server_default=sa.text('20'), autoincrement=False, nullable=False))
    op.add_column('notification_preferences', sa.Column('sleep_reminder_hour', sa.INTEGER(), server_default=sa.text('21'), autoincrement=False, nullable=False))
    op.add_column('notification_preferences', sa.Column('workout_reminder_hour', sa.INTEGER(), server_default=sa.text('7'), autoincrement=False, nullable=False))
    op.add_column('notification_preferences', sa.Column('workout_reminders_enabled', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False))
