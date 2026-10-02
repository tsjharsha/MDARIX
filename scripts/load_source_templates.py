"""Set up one tenant in the simulated customer systems and load its CSV files.

For every application (TrackWise, Teamcenter, SAP, ...) this creates the tenant there, with its own database and API
key, then uploads each CSV file of that application. By default it loads the MDARIX templates in
data/source-templates; point --data at your own folder with the same layout (<APPLICATION>/<record>.csv) to load
your data. API keys are shown once by the simulators: they are written to --keys (keep that file private; it is
needed to connect MDARIX and is never committed).

Usage:
  python scripts/load_source_templates.py --tenant ACME_MEDICAL --keys %USERPROFILE%/acme-source-keys.json
  python scripts/load_source_templates.py --tenant ACME_MEDICAL --keys keys.json --data D:/acme-data --apps SAP_ERP,MES
The simulators' admin token comes from MDARIX_SIMULATOR_ADMIN_TOKEN (the value in .env used by docker compose).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "source_simulator" / "source_catalog.json").read_text(encoding="utf-8"))
STANDARD = json.loads((ROOT / "backend" / "app" / "access" / "standard_mappings.json").read_text(encoding="utf-8"))


def call(method: str, url: str, headers: dict, body: bytes | None = None) -> tuple[int, dict]:
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}


def load_order(application: str) -> list[str]:
    """The application's records in the order their MDARIX records should be loaded."""
    ordered = [item["record"] for item in STANDARD if item["application"] == application]
    rest = [name for name in CATALOG[application]["records"] if name not in ordered]
    return list(dict.fromkeys(ordered + rest))


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a tenant in the simulated customer systems and load CSVs.")
    parser.add_argument("--tenant", required=True, help="tenant key in the simulators, e.g. ACME_MEDICAL")
    parser.add_argument("--keys", required=True, help="file to write the API keys to (keep it private)")
    parser.add_argument("--data", default=str(ROOT / "data" / "source-templates"), help="folder of CSV files")
    parser.add_argument("--apps", default="", help="comma-separated applications (default: every one)")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    admin_token = os.getenv("MDARIX_SIMULATOR_ADMIN_TOKEN", "")
    if not admin_token:
        print("Set MDARIX_SIMULATOR_ADMIN_TOKEN to the simulators' admin token (see .env).")
        return 2
    tenant = args.tenant.strip().upper()
    applications = [app.strip().upper() for app in args.apps.split(",") if app.strip()] or list(CATALOG)
    keys_path = Path(args.keys)
    keys = json.loads(keys_path.read_text(encoding="utf-8")) if keys_path.exists() else {}
    data = Path(args.data)
    failures = 0
    for application in applications:
        if application not in CATALOG:
            print(f"{application}: not a simulated system ({', '.join(CATALOG)})")
            failures += 1
            continue
        base = f"http://{args.host}:{CATALOG[application]['port']}"
        if application not in keys.get(tenant, {}):
            status, body = call(
                "POST",
                f"{base}/admin/tenants",
                {"X-Admin-Token": admin_token, "Content-Type": "application/json"},
                json.dumps({"tenant_key": tenant}).encode(),
            )
            if status == 409:
                print(f"{application}: {tenant} already exists; add its key to {keys_path} or rotate it")
                failures += 1
                continue
            if status != 201:
                print(f"{application}: tenant not created ({status} {body.get('detail', body)})")
                failures += 1
                continue
            keys.setdefault(tenant, {})[application] = {"endpoint": base, "api_key": body["api_key"]}
            keys_path.write_text(json.dumps(keys, indent=1), encoding="utf-8")
            print(f"{application}: tenant {tenant} created with its own database ({body['database']})")
        api_key = keys[tenant][application]["api_key"]
        for record in load_order(application):
            path = data / application / f"{record}.csv"
            if not path.exists():
                continue
            status, body = call(
                "POST",
                f"{base}/records/{record}/csv",
                {"X-Provider-Token": api_key, "Content-Type": "text/csv"},
                path.read_bytes(),
            )
            if status == 200:
                print(f"  {record}: {body['rows']} rows ({body['created']} new, {body['updated']} changed)")
            else:
                failures += 1
                detail = body.get("detail", {})
                problems = detail.get("problems", []) if isinstance(detail, dict) else []
                print(f"  {record}: refused ({status}) {detail if not problems else ''}")
                for problem in problems[:10]:
                    print(f"    row {problem['row']}: {problem['message']}")
    print(
        f"API keys for {tenant} are in {keys_path}. Connect MDARIX with them (docs/runbooks/CUSTOMER_SOURCE_SYSTEMS.md)."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
