"""Phase 3 data model (spec §4.1-§4.7).

Revision ID: 007
Revises: 006
Create Date: 2026-10-12

Adds, never replaces: the eight existing tables are untouched (§4).
Generated from the models with Alembic's autogenerate API and then reviewed:
  - Boolean server defaults use sa.true()/sa.false(); the rendered text('1')
    is not a valid boolean default on PostgreSQL.
  - credit_ledger gets an append-only trigger (the same DDL as
    app/models/billing.py, which installs it for create_all).
`alembic check` in the boot check proves the models and this file agree;
CHECK constraints and triggers are not compared by it, so the boot check also
probes them on the real database (PostgreSQL in CI).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.billing import CREDIT_LEDGER_GUARD_PG, CREDIT_LEDGER_GUARD_SQLITE

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cabinets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('marina_id', sa.Integer(), nullable=False),
    sa.Column('pedestal_pk', sa.Integer(), nullable=False),
    sa.Column('display_id', sa.String(length=100), nullable=False),
    sa.Column('device_type', sa.String(length=20), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=False),
    sa.Column('service_email', sa.String(length=320), nullable=False),
    sa.Column('service_pw_enc', sa.Text(), nullable=False),
    sa.Column('erp_api_key_enc', sa.Text(), nullable=True),
    sa.Column('dock', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("device_type IN ('full', 'retrofit')", name='ck_cabinets_device_type'),
    sa.ForeignKeyConstraint(['marina_id'], ['marinas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('marina_id', 'display_id', name='uq_cabinets_marina_display'),
    sa.UniqueConstraint('marina_id', 'pedestal_pk', name='uq_cabinets_marina_pk')
    )
    op.create_table('customers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('marina_id', sa.Integer(), nullable=False),
    sa.Column('external_ref', sa.String(length=100), nullable=True),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['marina_id'], ['marinas.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('marina_id', 'external_ref', name='uq_customers_marina_ref')
    )
    op.create_table('marina_billing_policy',
    sa.Column('marina_id', sa.Integer(), nullable=False),
    sa.Column('min_start_amount', sa.Numeric(precision=10, scale=2), server_default=sa.text('1.00'), nullable=False),
    sa.Column('allowed_negative', sa.Numeric(precision=10, scale=2), server_default=sa.text('-2.00'), nullable=False),
    sa.Column('low_credit_warn_pct', sa.Integer(), server_default='20', nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['marina_id'], ['marinas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('marina_id')
    )
    op.create_table('tariffs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('marina_id', sa.Integer(), nullable=False),
    sa.Column('medium', sa.String(length=20), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
    sa.Column('vat_rate', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('time_band', sa.String(length=10), nullable=True),
    sa.Column('band_from', sa.String(length=5), nullable=True),
    sa.Column('band_to', sa.String(length=5), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.CheckConstraint("medium IN ('electricity', 'water')", name='ck_tariffs_medium'),
    sa.ForeignKeyConstraint(['marina_id'], ['marinas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('marina_id', 'medium', 'time_band', 'valid_from', name='uq_tariffs_band')
    )
    op.create_table('berth_outlets_cabinet',
    sa.Column('cabinet_id', sa.Integer(), nullable=False),
    sa.Column('outlet_name', sa.String(length=2), nullable=False),
    sa.Column('cabinet_berth_id', sa.Integer(), nullable=True),
    sa.Column('assigned_by', sa.String(length=320), nullable=True),
    sa.Column('assigned_at', sa.DateTime(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['cabinet_id'], ['cabinets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('cabinet_id', 'outlet_name')
    )
    op.create_table('berths',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('marina_id', sa.Integer(), nullable=False),
    sa.Column('berth_number', sa.String(length=50), nullable=False),
    sa.Column('svg_id', sa.String(length=100), nullable=True),
    sa.Column('cabinet_id', sa.Integer(), nullable=True),
    sa.Column('cabinet_berth_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['cabinet_id'], ['cabinets.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['marina_id'], ['marinas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cabinet_id', 'cabinet_berth_id', name='uq_berths_cabinet_berth'),
    sa.UniqueConstraint('marina_id', 'berth_number', name='uq_berths_marina_number')
    )
    op.create_table('cabinet_capabilities',
    sa.Column('cabinet_id', sa.Integer(), nullable=False),
    sa.Column('capability', sa.String(length=30), nullable=False),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('checked_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("capability IN ('power', 'water', 'vessel_detect', 'camera', 'door', 'breaker', 'load_meter')", name='ck_capability_name'),
    sa.ForeignKeyConstraint(['cabinet_id'], ['cabinets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('cabinet_id', 'capability')
    )
    op.create_table('contracts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('billing_mode', sa.String(length=10), server_default='prepaid', nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('blocked', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('max_unpaid', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('max_kwh_session', sa.Numeric(precision=10, scale=3), nullable=True),
    sa.Column('max_session_min', sa.Integer(), nullable=True),
    sa.Column('tariff_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("billing_mode IN ('prepaid', 'postpaid')", name='ck_contracts_mode'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tariff_id'], ['tariffs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('credit_ledger',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('delta', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('reason', sa.String(length=20), nullable=False),
    sa.Column('session_id', sa.BigInteger(), nullable=True),
    sa.Column('balance_after', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('created_by', sa.String(length=320), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("reason <> 'consumption' OR session_id IS NOT NULL", name='ck_credit_consumption_has_session'),
    sa.CheckConstraint("reason IN ('topup', 'consumption', 'adjustment', 'refund')", name='ck_credit_reason'),
    sa.CheckConstraint('length(trim(created_by)) > 0', name='ck_credit_created_by'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_credit_ledger_customer_id'), 'credit_ledger', ['customer_id'], unique=False)
    op.create_table('mapping_comparison',
    sa.Column('cabinet_id', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('divergent_rows', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('checked_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("state IN ('unverifiable', 'in_sync', 'divergent')", name='ck_mapping_comparison_state'),
    sa.ForeignKeyConstraint(['cabinet_id'], ['cabinets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('cabinet_id')
    )
    op.create_table('outlets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cabinet_id', sa.Integer(), nullable=False),
    sa.Column('outlet_name', sa.String(length=2), nullable=False),
    sa.Column('medium', sa.String(length=20), nullable=False),
    sa.Column('phases', sa.Integer(), nullable=True),
    sa.Column('rated_amps', sa.Integer(), nullable=True),
    sa.Column('rated_lpm', sa.Integer(), nullable=True),
    sa.CheckConstraint("(substr(outlet_name, 1, 1) = 'Q' AND medium = 'electricity') OR (substr(outlet_name, 1, 1) = 'V' AND medium = 'water')", name='ck_outlets_medium_matches_name'),
    sa.CheckConstraint("medium = 'electricity' OR (phases IS NULL AND rated_amps IS NULL)", name='ck_outlets_water_has_no_phases'),
    sa.CheckConstraint("outlet_name IN ('Q1', 'Q2', 'Q3', 'Q4', 'V1', 'V2')", name='ck_outlets_name'),
    sa.CheckConstraint('phases IS NULL OR phases IN (1, 3)', name='ck_outlets_phases'),
    sa.ForeignKeyConstraint(['cabinet_id'], ['cabinets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cabinet_id', 'outlet_name', name='uq_outlets_cabinet_name'),
    sa.UniqueConstraint('id', 'medium', name='uq_outlets_id_medium')
    )
    op.create_table('berth_outlets',
    sa.Column('berth_id', sa.Integer(), nullable=False),
    sa.Column('outlet_id', sa.Integer(), nullable=False),
    sa.Column('medium', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('assigned_by', sa.String(length=320), nullable=False),
    sa.Column('assigned_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("source IN ('erp_manual', 'cabinet', 'confirmed')", name='ck_berth_outlets_source'),
    sa.CheckConstraint('length(trim(assigned_by)) > 0', name='ck_berth_outlets_assigned_by'),
    sa.ForeignKeyConstraint(['berth_id'], ['berths.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['outlet_id', 'medium'], ['outlets.id', 'outlets.medium'], name='fk_berth_outlets_outlet_medium', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('berth_id', 'outlet_id')
    )
    op.create_index('uq_berth_outlets_electric_berth', 'berth_outlets', ['berth_id'], unique=True, postgresql_where=sa.text("medium = 'electricity'"), sqlite_where=sa.text("medium = 'electricity'"))
    op.create_index('uq_berth_outlets_electric_outlet', 'berth_outlets', ['outlet_id'], unique=True, postgresql_where=sa.text("medium = 'electricity'"), sqlite_where=sa.text("medium = 'electricity'"))
    op.create_table('command_audit',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('cabinet_id', sa.Integer(), nullable=False),
    sa.Column('outlet_id', sa.Integer(), nullable=True),
    sa.Column('endpoint_key', sa.String(length=100), nullable=False),
    sa.Column('action', sa.String(length=30), nullable=False),
    sa.Column('actor_type', sa.String(length=20), nullable=False),
    sa.Column('actor_ref', sa.String(length=320), nullable=True),
    sa.Column('tag_source', sa.String(length=10), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('request_url', sa.Text(), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('source_ip', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("actor_type <> 'operator' OR (reason IS NOT NULL AND length(trim(reason)) > 0)", name='ck_command_audit_operator_reason'),
    sa.CheckConstraint("actor_type IN ('customer_nfc', 'operator', 'erp_auto')", name='ck_command_audit_actor'),
    sa.CheckConstraint("tag_source IS NULL OR tag_source IN ('scan', 'mapping')", name='ck_command_audit_tag_source'),
    sa.ForeignKeyConstraint(['cabinet_id'], ['cabinets.id'], ),
    sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_command_audit_created_at'), 'command_audit', ['created_at'], unique=False)
    op.create_table('outlet_nfc_tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('outlet_id', sa.Integer(), nullable=False),
    sa.Column('uid_primary', sa.String(length=64), nullable=False),
    sa.Column('uid_reversed', sa.String(length=64), nullable=False),
    sa.Column('tag_standard', sa.String(length=20), server_default='ISO15693', nullable=False),
    sa.Column('provisioned_by', sa.String(length=320), nullable=False),
    sa.Column('provisioned_at', sa.DateTime(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.CheckConstraint('length(trim(provisioned_by)) > 0', name='ck_nfc_provisioned_by'),
    sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uid_primary', name='uq_nfc_uid_primary'),
    sa.UniqueConstraint('uid_reversed', name='uq_nfc_uid_reversed')
    )
    op.create_table('sessions',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('erp_ref', sa.String(length=64), nullable=False),
    sa.Column('cabinet_id', sa.Integer(), nullable=False),
    sa.Column('cabinet_session_id', sa.Integer(), nullable=True),
    sa.Column('outlet_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('session_type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('activated_at', sa.DateTime(), nullable=True),
    sa.Column('ended_at', sa.DateTime(), nullable=True),
    sa.Column('duration_min', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('energy_kwh', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('water_liters', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('meter_e_start', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('meter_e_end', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('meter_w_start', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('meter_w_end', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('consumption_source', sa.String(length=20), nullable=True),
    sa.Column('recompute_ok', sa.Boolean(), nullable=True),
    sa.Column('billing_state', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("billing_state <> 'billed' OR (session_type = 'electricity' AND energy_kwh IS NOT NULL) OR (session_type = 'water' AND water_liters IS NOT NULL)", name='ck_sessions_billed_has_figure'),
    sa.CheckConstraint("billing_state IN ('pending', 'billed', 'manual_review', 'not_billable')", name='ck_sessions_billing_state'),
    sa.CheckConstraint("consumption_source IS NULL OR consumption_source IN ('register', 'integrated_legacy', 'unknown')", name='ck_sessions_source'),
    sa.CheckConstraint("session_type IN ('electricity', 'water')", name='ck_sessions_type'),
    sa.CheckConstraint("status IN ('reserved', 'active', 'ended')", name='ck_sessions_status'),
    sa.ForeignKeyConstraint(['cabinet_id'], ['cabinets.id'], ),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cabinet_id', 'cabinet_session_id', name='uq_sessions_cabinet_session'),
    sa.UniqueConstraint('erp_ref', name='uq_sessions_erp_ref')
    )
    op.create_table('billing_records',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.BigInteger(), nullable=True),
    sa.Column('medium', sa.String(length=20), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('vat_rate', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('amount_net', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('amount_gross', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('tariff_id', sa.Integer(), nullable=False),
    sa.Column('issued_at', sa.DateTime(), nullable=False),
    sa.Column('exported_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("medium IN ('electricity', 'water')", name='ck_billing_medium'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.ForeignKeyConstraint(['tariff_id'], ['tariffs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('consumption_intervals',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('session_id', sa.BigInteger(), nullable=False),
    sa.Column('from_at', sa.DateTime(), nullable=False),
    sa.Column('to_at', sa.DateTime(), nullable=False),
    sa.Column('energy_kwh', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('water_liters', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consumption_intervals_session_id'), 'consumption_intervals', ['session_id'], unique=False)

    guard = CREDIT_LEDGER_GUARD_PG if op.get_bind().dialect.name == "postgresql"         else CREDIT_LEDGER_GUARD_SQLITE
    for stmt in guard:
        op.execute(stmt)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS credit_ledger_no_update ON credit_ledger")
        op.execute("DROP FUNCTION IF EXISTS credit_ledger_append_only()")
    op.drop_table('consumption_intervals')
    op.drop_table('billing_records')
    op.drop_table('sessions')
    op.drop_table('outlet_nfc_tags')
    op.drop_table('command_audit')
    op.drop_table('berth_outlets')
    op.drop_table('outlets')
    op.drop_table('mapping_comparison')
    op.drop_table('credit_ledger')
    op.drop_table('contracts')
    op.drop_table('cabinet_capabilities')
    op.drop_table('berths')
    op.drop_table('berth_outlets_cabinet')
    op.drop_table('tariffs')
    op.drop_table('marina_billing_policy')
    op.drop_table('customers')
    op.drop_table('cabinets')
