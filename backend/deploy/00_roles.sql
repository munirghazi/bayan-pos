-- Run ONCE per environment as a Postgres superuser (e.g. the 'postgres' user):
--   sudo -u postgres psql -v owner_pw="'...'" -v app_pw="'...'" -f deploy/00_roles.sql
-- (Edit the two passwords below if you prefer to hard-code them instead.)

\if :{?owner_pw} \else \set owner_pw '''CHANGE_ME_OWNER''' \endif
\if :{?app_pw}   \else \set app_pw   '''CHANGE_ME_APP'''   \endif

CREATE ROLE pos_owner LOGIN PASSWORD :owner_pw;
CREATE ROLE pos_app   LOGIN PASSWORD :app_pw;

-- UTF-8 database (Arabic content). Debian 12 default locale supports C.UTF-8.
CREATE DATABASE pos OWNER pos_owner
    ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';
GRANT CONNECT ON DATABASE pos TO pos_app;

\connect pos
ALTER SCHEMA public OWNER TO pos_owner;
GRANT USAGE ON SCHEMA public TO pos_app;
-- Table/sequence grants + RLS are applied by the Alembic migration
-- (run:  APP_DB_ROLE=pos_app alembic upgrade head).
