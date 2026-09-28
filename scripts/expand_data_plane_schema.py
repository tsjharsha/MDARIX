"""Expand each synthetic data plane from the current MDARIX schema.

The nine bootstrap business tables are excluded because they already contain
validated synthetic canaries. The operation is schema-only and does not copy
control-plane data or credentials.
"""
from __future__ import annotations

import subprocess


PLANES = [
    ("mdarix-r1-tenant-a-data-1", "mdarix_tenant_a"),
    ("mdarix-r1-tenant-b-data-1", "mdarix_tenant_b"),
    ("mdarix-r1-tenant-c-data-1", "mdarix_tenant_c"),
    ("mdarix-r1-tenant-d-data-1", "mdarix_tenant_d"),
]
BOOTSTRAP_TABLES = (
    "source_records", "products", "product_versions", "components", "suppliers",
    "lot_batches", "complaints", "investigations", "evidence",
)


def run(*args: str, input_data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, input=input_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def main() -> None:
    excludes = [arg for table in BOOTSTRAP_TABLES for arg in ("--exclude-table", f"public.{table}")]
    dump = run(
        "docker", "exec", "mdarix-r1-postgres", "pg_dump",
        "-U", "mdarix_app", "-d", "mdarix_r1", "--schema-only", "--format=custom",
        "--no-owner", "--no-privileges", *excludes,
    ).stdout
    for container, database in PLANES:
        # Restore is schema-only and intentionally does not use --clean.
        try:
            restored = run(
                "docker", "exec", "-i", container, "pg_restore", "-U", "mdarix_data",
                "-d", database, "--schema-only", "--no-owner", "--no-privileges",
                "--clean", "--if-exists", "--exit-on-error", input_data=dump,
            )
            for table in BOOTSTRAP_TABLES:
                constraint = f"{table}_tenant_id_key"
                sql = ("DO $$ BEGIN "
                       f"IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{constraint}') THEN "
                       f"ALTER TABLE {table} ADD CONSTRAINT {constraint} UNIQUE (tenant_id, id); "
                       "END IF; END $$;")
                run("docker", "exec", container, "psql", "-U", "mdarix_data", "-d", database, "-c", sql, input_data=None)
            # Data planes intentionally do not contain control-plane tenant
            # rows. Remove every copied FK whose target is the control-plane
            # tenants table; tenant identity is enforced by the registry and
            # application/data-plane policies at this boundary.
            drop_cross_plane_fks = """DO $$ DECLARE r record; BEGIN
              FOR r IN SELECT n.nspname, c.relname, con.conname
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_class parent ON parent.oid = con.confrelid
                WHERE con.contype = 'f' AND parent.relname = 'tenants'
              LOOP EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I', r.nspname, r.relname, r.conname); END LOOP;
            END $$;"""
            run("docker", "exec", container, "psql", "-U", "mdarix_data", "-d", database, "-c", drop_cross_plane_fks, input_data=None)
        except subprocess.CalledProcessError as exc:
            print(exc.stderr.decode(errors="replace"))
            raise
        print(f"EXPANDED {database}: {len(restored.stdout)} bytes")


if __name__ == "__main__":
    main()
