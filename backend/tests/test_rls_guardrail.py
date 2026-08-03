"""Guardrail: EVERY table with a tenant_id column must have RLS enabled, FORCED,
and at least one policy. This fails automatically if a future migration adds a
tenant-scoped table but forgets to isolate it.
"""
import psycopg2
from config import settings

RAW_DSN = settings.database_url.replace("+psycopg2", "")


def test_all_tenant_tables_are_isolated():
    c = psycopg2.connect(RAW_DSN)
    cur = c.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name = 'tenant_id'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    assert tables, "no tenant-scoped tables found — schema not migrated?"

    problems = []
    for t in tables:
        cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (t,))
        rls, forced = cur.fetchone()
        cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename = %s", (t,))
        policies = cur.fetchone()[0]
        if not rls or not forced or policies < 1:
            problems.append(f"  {t}: rls={rls} forced={forced} policies={policies}")
    c.close()

    assert not problems, (
        "These tenant-scoped tables are NOT properly isolated:\n"
        + "\n".join(problems)
        + "\n(enable + FORCE row level security and add a tenant_isolation policy)"
    )
