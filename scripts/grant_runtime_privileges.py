"""Give the application roles exactly the privileges they need (database owner credentials; safe to run any time).

The runtime role may read and write every application table (row-level security still limits it to one tenant) and
call ``mdarix_system_scope()``, but never read the system-scope secret, nor write the tables without row-level
security that steer numbering and the schema stamp (``business_id_counters``, ``alembic_version``). The read-only role may only read. Run by the
migrate job on every deploy, and after a restore (backups are taken without privileges).

    python scripts/grant_runtime_privileges.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from backend.app.db.session import engine  # noqa: E402

GRANTS = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN
    GRANT USAGE ON SCHEMA public TO mdarix_runtime;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mdarix_runtime;
    GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO mdarix_runtime;
    GRANT EXECUTE ON FUNCTION public.mdarix_system_scope() TO mdarix_runtime;
    REVOKE ALL ON public.mdarix_rls_secret FROM mdarix_runtime;
    -- No row-level security on these, so read only (DB-1, tr21): the md26 trigger writes the counters as owner.
    REVOKE INSERT, UPDATE, DELETE ON public.alembic_version, public.business_id_counters FROM mdarix_runtime;
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'md_master') THEN
      GRANT USAGE ON SCHEMA md_master TO mdarix_runtime;
      GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA md_master TO mdarix_runtime;
      GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA md_master TO mdarix_runtime;
    END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_readonly') THEN
    GRANT USAGE ON SCHEMA public TO mdarix_readonly;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO mdarix_readonly;
    GRANT EXECUTE ON FUNCTION public.mdarix_system_scope() TO mdarix_readonly;
    REVOKE ALL ON public.mdarix_rls_secret FROM mdarix_readonly;
  END IF;
  REVOKE ALL ON public.mdarix_rls_secret FROM PUBLIC;
  REVOKE ALL ON FUNCTION public.mdarix_system_scope() FROM PUBLIC;
END $$;
"""


def main() -> int:
    with engine.begin() as connection:
        connection.execute(text(GRANTS))
        runtime_ok = connection.execute(
            text(
                "SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') OR "
                "(has_table_privilege('mdarix_runtime', 'public.tenants', 'SELECT') AND "
                "NOT has_table_privilege('mdarix_runtime', 'public.mdarix_rls_secret', 'SELECT') AND "
                "NOT has_table_privilege('mdarix_runtime', 'public.business_id_counters', 'UPDATE') AND "
                "NOT has_table_privilege('mdarix_runtime', 'public.alembic_version', 'UPDATE'))"
            )
        ).scalar()
    if not runtime_ok:
        print("Runtime role privileges are not as expected.", file=sys.stderr)
        return 1
    print("Application role privileges applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
