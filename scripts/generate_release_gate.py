"""Generate an evidence-backed local GO/NO-GO report."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

def main() -> int:
    root = Path('artifacts')
    stack = root / 'local-stack-validation.json'
    data = json.loads(stack.read_text(encoding='utf-8')) if stack.exists() else {}
    ready = bool(data.get('http', {}).get('frontend', {}).get('reachable')) and bool(data.get('http', {}).get('backend_live', {}).get('reachable'))
    status = 'GO_FOR_CONTROLLED_LOCAL_DEMO' if ready else 'NO_GO'
    root.mkdir(exist_ok=True)
    (root / 'automated-release-gate.md').write_text(f'''# MDARIX automated release gate

Generated: {datetime.now(timezone.utc).isoformat()}

## Decision

**{status}**

This is a controlled local validation decision only, not a production-readiness claim.

## Evidence

- Local stack report: {'present' if stack.exists() else 'missing'}
- Backend/frontend readiness: {'PASS' if ready else 'PENDING'}

## External gates

- Production PostgreSQL TLS/runtime role
- Backup, restore, PITR, and retention rehearsal
- Monitoring and alert delivery
- Multi-instance deployment/session validation
- Real SMTP/provider and customer connector validation
- Production object storage and malware scanning
- Manual screen-reader review
''', encoding='utf-8')
    return 0 if ready else 1

if __name__ == '__main__':
    raise SystemExit(main())
