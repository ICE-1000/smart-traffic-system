-- Run once as the postgres superuser (psql -U postgres -f database/setup_postgres.sql)
-- then set DATABASE_URL=postgresql+psycopg://traffic:CHANGE_ME@localhost:5432/traffic in backend/.env
CREATE ROLE traffic LOGIN PASSWORD 'CHANGE_ME';
CREATE DATABASE traffic OWNER traffic;
