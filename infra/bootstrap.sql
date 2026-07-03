-- meetgraph — one-time Postgres bootstrap (run as superuser, e.g. via pgAdmin/psql)
-- App schema DB + cognee DB on the same instance (§8 single-Postgres).

-- CREATEDB is required: cognee (access-control mode) creates a database per
-- dataset — this is the physical tenant-isolation mechanism (see §8 / research).
CREATE ROLE meetgraph LOGIN PASSWORD 'meetgraph' CREATEDB;
-- DEV ONLY: cognee also runs CREATE EXTENSION vector inside each dataset DB,
-- which needs superuser unless vector.control has `trusted = true`. On dev:
--   ALTER ROLE meetgraph SUPERUSER;
-- In production, add `trusted = true` to vector.control instead and keep the
-- role unprivileged.

CREATE DATABASE meetgraph OWNER meetgraph;
CREATE DATABASE meetgraph_cognee OWNER meetgraph;

-- pgvector must be installed on the server first (Windows: see infra/pgvector-windows.md)
\connect meetgraph_cognee
CREATE EXTENSION IF NOT EXISTS vector;

\connect meetgraph
-- app schema itself needs no extensions; alembic creates tables.
