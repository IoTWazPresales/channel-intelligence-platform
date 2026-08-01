"""Add lineup planning and promo plan export tables.

Revision ID: 20260412_0002
Revises: 20260412_0001
Create Date: 2026-04-12

"""

from typing import Sequence, Union

from alembic import op

from app.models.lineup import FactLineupPlanItem
from app.models.promo_export import PromoPlanExport, PromoPlanExportEvent

revision: str = "20260412_0002"
down_revision: Union[str, Sequence[str], None] = "20260412_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    FactLineupPlanItem.__table__.create(bind=bind, checkfirst=True)
    PromoPlanExport.__table__.create(bind=bind, checkfirst=True)
    PromoPlanExportEvent.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    PromoPlanExportEvent.__table__.drop(bind=bind, checkfirst=True)
    PromoPlanExport.__table__.drop(bind=bind, checkfirst=True)
    FactLineupPlanItem.__table__.drop(bind=bind, checkfirst=True)
