-- One database per service (Conventions §2 — services never share a schema).
-- Run once by the postgres image on first start of an empty data volume.
--
-- Locally these live in one Postgres instance for convenience; in production
-- they are logically separate databases. Whether they stay co-located on-prem is
-- register D4, still open — nothing in the application code depends on it.
--
-- The Worker has no database here on purpose: it owns no tables and must not
-- read another service's.

CREATE DATABASE collabhub_auth;
CREATE DATABASE collabhub_messaging;
CREATE DATABASE collabhub_canvas;
CREATE DATABASE collabhub_asset;

-- Extensions belong to the migration that needs them (Auth's `users.email` is
-- `citext`), so they are not created here.
