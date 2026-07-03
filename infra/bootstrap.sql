-- meetgraph — one-time Postgres bootstrap (run as superuser, e.g. via pgAdmin/psql)
-- App schema DB + cognee DB on the same instance (§8 single-Postgres).

CREATE ROLE meetgraph LOGIN PASSWORD 'meetgraph';

CREATE DATABASE meetgraph OWNER meetgraph;
CREATE DATABASE meetgraph_cognee OWNER meetgraph;

-- pgvector must be installed on the server first (Windows: see infra/pgvector-windows.md)
\connect meetgraph_cognee
CREATE EXTENSION IF NOT EXISTS vector;

\connect meetgraph
-- app schema itself needs no extensions; alembic creates tables.
