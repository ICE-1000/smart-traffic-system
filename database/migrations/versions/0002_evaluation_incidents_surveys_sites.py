"""Evaluation snapshots, incidents, field surveys, validation counts, study-site fields, CI columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-25 14:08:20.944474
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('evaluation_snapshots',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ts', sa.Float(), nullable=False),
    sa.Column('intersection_id', sa.String(length=32), nullable=False),
    sa.Column('run_started', sa.Float(), nullable=False),
    sa.Column('elapsed_s', sa.Float(), nullable=False),
    sa.Column('sources', sa.String(length=32), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('evaluation_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evaluation_snapshots_intersection_id'), ['intersection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evaluation_snapshots_run_started'), ['run_started'], unique=False)
        batch_op.create_index(batch_op.f('ix_evaluation_snapshots_ts'), ['ts'], unique=False)

    op.create_table('incidents',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('intersection_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('approach', sa.String(length=10), nullable=True),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('started', sa.Float(), nullable=False),
    sa.Column('ended', sa.Float(), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('acknowledged', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_incidents_intersection_id'), ['intersection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidents_started'), ['started'], unique=False)

    op.create_table('survey_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created', sa.Float(), nullable=False),
    sa.Column('intersection_id', sa.String(length=32), nullable=False),
    sa.Column('corridor', sa.String(length=120), nullable=False),
    sa.Column('direction', sa.String(length=40), nullable=False),
    sa.Column('run_time', sa.Float(), nullable=False),
    sa.Column('distance_km', sa.Float(), nullable=False),
    sa.Column('tw_min', sa.Float(), nullable=False),
    sa.Column('ta_min', sa.Float(), nullable=False),
    sa.Column('x', sa.Float(), nullable=False),
    sa.Column('y', sa.Float(), nullable=False),
    sa.Column('free_flow_kmh', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('survey_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_survey_runs_intersection_id'), ['intersection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_survey_runs_run_time'), ['run_time'], unique=False)

    op.create_table('validation_counts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created', sa.Float(), nullable=False),
    sa.Column('intersection_id', sa.String(length=32), nullable=False),
    sa.Column('camera_id', sa.String(length=32), nullable=False),
    sa.Column('start_ts', sa.Float(), nullable=False),
    sa.Column('end_ts', sa.Float(), nullable=False),
    sa.Column('manual_count', sa.Integer(), nullable=False),
    sa.Column('manual_mean_wait_s', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('validation_counts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_validation_counts_intersection_id'), ['intersection_id'], unique=False)

    with op.batch_alter_table('intersections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('node_type', sa.String(length=16), nullable=False, server_default='signalised'))
        batch_op.add_column(sa.Column('corridor', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))

    with op.batch_alter_table('traffic_measurements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mean_delay_s', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('congestion_index', sa.Float(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('traffic_measurements', schema=None) as batch_op:
        batch_op.drop_column('congestion_index')
        batch_op.drop_column('mean_delay_s')

    with op.batch_alter_table('intersections', schema=None) as batch_op:
        batch_op.drop_column('description')
        batch_op.drop_column('corridor')
        batch_op.drop_column('node_type')

    with op.batch_alter_table('validation_counts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_validation_counts_intersection_id'))

    op.drop_table('validation_counts')
    with op.batch_alter_table('survey_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_survey_runs_run_time'))
        batch_op.drop_index(batch_op.f('ix_survey_runs_intersection_id'))

    op.drop_table('survey_runs')
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_incidents_started'))
        batch_op.drop_index(batch_op.f('ix_incidents_intersection_id'))

    op.drop_table('incidents')
    with op.batch_alter_table('evaluation_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evaluation_snapshots_ts'))
        batch_op.drop_index(batch_op.f('ix_evaluation_snapshots_run_started'))
        batch_op.drop_index(batch_op.f('ix_evaluation_snapshots_intersection_id'))

    op.drop_table('evaluation_snapshots')
