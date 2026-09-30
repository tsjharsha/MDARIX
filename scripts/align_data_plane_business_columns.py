"""Add missing business columns to the preserved synthetic bootstrap tables."""

from __future__ import annotations

import subprocess

TABLES = (
    "source_records",
    "products",
    "product_versions",
    "components",
    "suppliers",
    "lot_batches",
    "complaints",
    "investigations",
    "evidence",
)
CONTAINERS = (
    "mdarix-r1-tenant-a-data-1",
    "mdarix-r1-tenant-b-data-1",
    "mdarix-r1-tenant-c-data-1",
    "mdarix-r1-tenant-d-data-1",
)
DATABASES = ("mdarix_tenant_a", "mdarix_tenant_b", "mdarix_tenant_c", "mdarix_tenant_d")


def docker(*args: str, input_data: bytes | None = None) -> bytes:
    return subprocess.run(
        ("docker", *args), input=input_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    ).stdout


def main() -> None:
    for container, database in zip(CONTAINERS, DATABASES):
        for table in TABLES:
            central = (
                docker(
                    "exec",
                    "mdarix-r1-postgres",
                    "psql",
                    "-U",
                    "mdarix_app",
                    "-d",
                    "mdarix_r1",
                    "-At",
                    "-F",
                    "\t",
                    "-c",
                    f"SELECT a.attname, pg_catalog.format_type(a.atttypid,a.atttypmod) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname='{table}' AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum",
                )
                .decode()
                .splitlines()
            )
            current = (
                docker(
                    "exec",
                    container,
                    "psql",
                    "-U",
                    "mdarix_data",
                    "-d",
                    database,
                    "-At",
                    "-c",
                    f"SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='{table}'",
                )
                .decode()
                .splitlines()
            )
            current_set = set(current)
            for line in central:
                name, sql_type = line.split("\t", 1)
                if name not in current_set:
                    docker(
                        "exec",
                        container,
                        "psql",
                        "-U",
                        "mdarix_data",
                        "-d",
                        database,
                        "-c",
                        f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}',
                    )
            print(f"ALIGNED {database}.{table}")


if __name__ == "__main__":
    main()
