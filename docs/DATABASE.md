# Database

Schema is managed by **Alembic** (`database/migrations/`). The backend runs
`alembic upgrade head` automatically at startup, for SQLite or PostgreSQL.

## SQLite (default)
Nothing to install. File: `data/traffic.db`. Fine for a single laptop and weeks of data.

## PostgreSQL (recommended for long runs / analysis)
1. Install PostgreSQL 16+ for Windows (EnterpriseDB installer from postgresql.org); remember the
   `postgres` password.
2. Create the database (SQL Shell / psql as postgres):
   ```sql
   CREATE ROLE traffic LOGIN PASSWORD 'choose-a-password';
   CREATE DATABASE traffic OWNER traffic;
   ```
   (or `psql -U postgres -f database/setup_postgres.sql` after editing the password)
3. In `backend/.env`:
   ```
   DATABASE_URL=postgresql+psycopg://traffic:choose-a-password@localhost:5432/traffic
   ```
4. Start the backend — tables are created by the migration.

Verified here against PostgreSQL 16: migration, live writes, settings persistence across
restart, history and CSV export.

## Tables
| Table | Written | Contents |
|---|---|---|
| intersections, cameras | on config change | registry, stream address, processing settings, regions (JSON) |
| traffic_measurements | every 5 s per approach | queue, length, waits, rates, in-view counts, simulated signal colour, **source** (vision/demo) |
| congestion_measurements | every 5 s per approach | score, category, normalised components, source |
| vehicle_detections | when a track ends | one row per vehicle: class, max confidence, last box, entered approach, departed, wait |
| priority_decisions | on change or every 30 s | recommendation, rule, generated reason, full ranking |
| signal_simulation_events | on change | phase start / yellow / all-red with reasons |
| app_settings | on operator change | congestion weights, signal timings, priority limits, AI config, data-source mode |
| system_events | on events | startup, camera saves, region updates, mode changes |
| incidents | on open / close | kind, approach, severity, start, end, message, acknowledged, data source |
| evaluation_snapshots | every 60 s | full adaptive-vs-fixed summary per run (run_started groups a run) |
| survey_runs | on entry | moving-car run pairs (inputs; results computed on read) |
| validation_counts | on entry | manual count sessions (system count computed on read from vehicle_detections) |

Migration **0002** adds the four tables above, `intersections.node_type / corridor / description`
and `traffic_measurements.mean_delay_s / congestion_index`. Existing rows are kept (tested);
the proposal's study nodes are inserted at start-up. All site-specific data carries `intersection_id`.

Approaches with no data are **not** written (no fabricated zeros). No video is stored.

## Retention
Rows older than `RETENTION_DAYS` (default 30) are deleted hourly.

## Upgrading from the Phase-1 build
A Phase-1 SQLite file (created without Alembic, demo data only) is automatically renamed to
`data/traffic.phase1-backup.db` and a fresh database is created.

## Schema changes
```powershell
# after editing backend/app/models/db.py
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```
