"""One-page summary of a security-scan release folder (scripts/security_scan.sh), kept as B10-1 evidence.

    python scripts/security_scan_summary.py security-reports/<release> --allowlist infrastructure/security-scan/allowlist.txt

Reads each tool's report, normalises every finding to (tool, severity, rule, location, title), removes the ones the
allow-list explains, and writes SUMMARY.md (counts per severity per tool; every Critical and High with an empty
decision line) and findings.json (every finding, for the record). Standard library only.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

SEVERITIES = ("Critical", "High", "Medium", "Low", "Info", "Unrated")
TOOLS = (
    "semgrep",
    "bandit",
    "pip-audit",
    "npm-audit",
    "gitleaks",
    "trivy",
    "zap-baseline",
    "zap-api",
    "schemathesis",
    "nuclei",
    "cross-tenant",
    "testssl",
    "observatory",
)


@dataclass(frozen=True)
class Finding:
    tool: str
    severity: str
    rule: str
    location: str
    title: str


@dataclass(frozen=True)
class AllowEntry:
    tool: str
    rule: str
    location: str
    reason: str

    def matches(self, finding: Finding) -> bool:
        return (
            self.tool == finding.tool
            and self.rule == finding.rule
            and (self.location == "*" or self.location in finding.location)
        )


def _sev(value: object) -> str:
    text = str(value or "").strip().lower()
    return {
        "critical": "Critical",
        "high": "High",
        "error": "High",
        "medium": "Medium",
        "moderate": "Medium",
        "warning": "Medium",
        "warn": "Medium",
        "low": "Low",
        "info": "Info",
        "informational": "Info",
        "note": "Info",
    }.get(text, "Unrated")


def _load_json(path: str) -> object | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _rel(path: str) -> str:
    for prefix in ("/src/", "/repo/"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path


def parse_semgrep(folder: str) -> list[Finding]:
    data = _load_json(os.path.join(folder, "semgrep.json")) or {}
    return [
        Finding(
            "semgrep",
            _sev(item.get("extra", {}).get("severity")),
            item.get("check_id", "?"),
            f"{_rel(item.get('path', '?'))}:{item.get('start', {}).get('line', '?')}",
            (item.get("extra", {}).get("message") or "").splitlines()[0][:160] if item.get("extra") else "",
        )
        for item in data.get("results", [])
    ]


def parse_bandit(folder: str) -> list[Finding]:
    data = _load_json(os.path.join(folder, "bandit.json")) or {}
    return [
        Finding(
            "bandit",
            _sev(item.get("issue_severity")),
            item.get("test_id", "?"),
            f"{_rel(item.get('filename', '?'))}:{item.get('line_number', '?')}",
            f"{item.get('issue_text', '')} (confidence {item.get('issue_confidence', '?').lower()})",
        )
        for item in data.get("results", [])
    ]


def parse_pip_audit(folder: str) -> list[Finding]:
    # pip-audit publishes no severity: each finding is "Unrated" and listed for a decision with its fix version.
    data = _load_json(os.path.join(folder, "pip-audit.json")) or {}
    found = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            fixes = ", ".join(vuln.get("fix_versions") or []) or "none"
            found.append(
                Finding(
                    "pip-audit",
                    "Unrated",
                    vuln.get("id", "?"),
                    f"{dep.get('name')}=={dep.get('version')}",
                    f"fix: {fixes}; aliases: {', '.join(vuln.get('aliases') or []) or '-'}",
                )
            )
    return found


def parse_npm_audit(folder: str) -> list[Finding]:
    data = _load_json(os.path.join(folder, "npm-audit.json")) or {}
    found = []
    for name, item in (data.get("vulnerabilities") or {}).items():
        advisories = [via for via in item.get("via", []) if isinstance(via, dict)]
        rule = ",".join(sorted({str(via.get("url", "")).rsplit("/", 1)[-1] for via in advisories})) or "via-dependency"
        fix = item.get("fixAvailable")
        found.append(
            Finding(
                "npm-audit",
                _sev(item.get("severity")),
                rule,
                f"{name} {item.get('range', '')}".strip(),
                (
                    advisories[0].get("title", "")
                    if advisories
                    else "through " + ", ".join(map(str, item.get("via", [])))
                )
                + f"; fix available: {'yes' if fix else 'no'}",
            )
        )
    return found


def parse_gitleaks(folder: str) -> list[Finding]:
    # Any secret in the history blocks the deploy until rotated, so every finding counts as High. Values are redacted.
    data = _load_json(os.path.join(folder, "gitleaks.json")) or []
    return [
        Finding(
            "gitleaks",
            "High",
            item.get("RuleID", "?"),
            f"{item.get('File', '?')}:{item.get('StartLine', '?')} @{str(item.get('Commit', ''))[:8]}",
            item.get("Description", ""),
        )
        for item in data
    ]


def parse_trivy(folder: str) -> list[Finding]:
    found = []
    for path in sorted(glob.glob(os.path.join(folder, "trivy-*.json"))):
        data = _load_json(path) or {}
        artifact = data.get("ArtifactName", os.path.basename(path))
        for result in data.get("Results") or []:
            target = result.get("Target", "")
            for vuln in result.get("Vulnerabilities") or []:
                fixed = vuln.get("FixedVersion") or "none"
                found.append(
                    Finding(
                        "trivy",
                        _sev(vuln.get("Severity")),
                        vuln.get("VulnerabilityID", "?"),
                        f"{artifact} {vuln.get('PkgName')} {vuln.get('InstalledVersion')}",
                        f"{(vuln.get('Title') or '')[:120]}; fixed in: {fixed}",
                    )
                )
            for item in result.get("Misconfigurations") or []:
                if item.get("Status") == "PASS":
                    continue
                line = (item.get("CauseMetadata") or {}).get("StartLine", "")
                found.append(
                    Finding(
                        "trivy",
                        _sev(item.get("Severity")),
                        item.get("ID") or item.get("AVDID", "?"),
                        f"{_rel(target)}:{line}" if line else _rel(target),
                        item.get("Title", ""),
                    )
                )
            for item in result.get("Secrets") or []:
                found.append(
                    Finding(
                        "trivy",
                        _sev(item.get("Severity")),
                        item.get("RuleID", "?"),
                        f"{artifact} {target}:{item.get('StartLine', '')}",
                        item.get("Title", ""),
                    )
                )
    return found


_ZAP_RISK = {"0": "Info", "1": "Low", "2": "Medium", "3": "High"}


def parse_zap(folder: str, tool: str, filename: str) -> list[Finding]:
    data = _load_json(os.path.join(folder, "zap", filename)) or {}
    found = []
    for site in data.get("site", []):
        for alert in site.get("alerts", []):
            instances = alert.get("instances") or [{}]
            uris = sorted({instance.get("uri", site.get("@name", "")) for instance in instances})
            location = uris[0] + (f" (+{len(uris) - 1} more)" if len(uris) > 1 else "")
            found.append(
                Finding(
                    tool,
                    _ZAP_RISK.get(str(alert.get("riskcode")), "Unrated"),
                    str(alert.get("pluginid", "?")),
                    location,
                    alert.get("name") or alert.get("alert", ""),
                )
            )
    return found


def _junit_problems(path: str) -> list[tuple[str, str, str]]:
    """(test name, "failure" or "error", message): a failure is a check that did not hold; an error is a test that
    could not run (for example its setup broke)."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []
    problems = []
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            for problem in case.findall(kind):
                message = (problem.get("message") or problem.text or "").strip()
                problems.append((case.get("name") or case.get("classname") or "?", kind, message))
    return problems


def _junit_failures(path: str) -> list[tuple[str, str]]:
    return [(name, message) for name, _kind, message in _junit_problems(path)]


# One JUnit failure holds every failed check of an operation: "1. Test Case ID: abc  - <check>  Received: ...".
_SCHEMATHESIS_CHECK = re.compile(r"\d+\. Test Case ID: \S+\s+-\s+(.+?)(?:\s{2,}|$)", re.MULTILINE)
# Server errors and authentication that was not enforced block the deploy (plan row 2); documentation mismatches
# (status codes or methods the OpenAPI file does not list) are Low; every other failed check is Medium.
_SCHEMATHESIS_HIGH = ("server error", "ignored auth", "without authentication", "authentication bypass")
_SCHEMATHESIS_LOW = (
    "undocumented http status code",
    "unsupported method incorrect response",
    "undocumented content-type",
)


def _schemathesis_severity(check: str) -> str:
    lowered = check.lower()
    if any(word in lowered for word in _SCHEMATHESIS_HIGH):
        return "High"
    if any(word in lowered for word in _SCHEMATHESIS_LOW):
        return "Low"
    return "Medium"


def parse_schemathesis(folder: str) -> list[Finding]:
    found = []
    for path in sorted(glob.glob(os.path.join(folder, "schemathesis", "*.xml"))):
        for operation, message in _junit_failures(path):
            checks = sorted(set(_SCHEMATHESIS_CHECK.findall(message))) or ["check failed"]
            for check in checks:
                found.append(Finding("schemathesis", _schemathesis_severity(check), check.strip(), operation, check))
    return found


def parse_nuclei(folder: str) -> list[Finding]:
    found = []
    try:
        with open(os.path.join(folder, "nuclei", "nuclei.jsonl"), encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
    except OSError:
        return found
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        info = item.get("info") or {}
        found.append(
            Finding(
                "nuclei",
                _sev(info.get("severity")),
                item.get("template-id", "?"),
                item.get("matched-at", ""),
                info.get("name", ""),
            )
        )
    return found


def parse_cross_tenant(folder: str) -> list[Finding]:
    # A failed cross-tenant test may mean one organization reads another's data: High, blocks the deploy. A test that
    # could not run (setup error) proves nothing either way: Medium, so the gap in coverage is still reported.
    found = []
    for name, kind, message in _junit_problems(os.path.join(folder, "cross-tenant.xml")):
        first = message.splitlines()[0][:160] if message else kind
        if kind == "failure":
            found.append(Finding("cross-tenant", "High", name, "tests", first))
        else:
            found.append(Finding("cross-tenant", "Medium", name, "tests", f"did not run: {first}"))
    return found


def parse_testssl(folder: str) -> list[Finding]:
    data = _load_json(os.path.join(folder, "testssl", "testssl.json")) or []
    found = []
    for item in data if isinstance(data, list) else []:
        severity = str(item.get("severity", "")).upper()
        if severity in ("OK", "INFO", "DEBUG", ""):
            continue
        found.append(
            Finding(
                "testssl", _sev(severity), item.get("id", "?"), item.get("ip", ""), str(item.get("finding", ""))[:160]
            )
        )
    return found


def parse_observatory(folder: str) -> list[Finding]:
    data = _load_json(os.path.join(folder, "observatory.json"))
    if not isinstance(data, dict) or "grade" not in data:
        return []
    failed = int(data.get("tests_failed") or 0)
    return [
        Finding(
            "observatory",
            "Info" if failed == 0 else "Low",
            "grade",
            str(data.get("details_url", "mdarix.com")),
            f"grade {data.get('grade')}, score {data.get('score')}, {failed} test(s) failed",
        )
    ]


PARSERS = {
    "semgrep": parse_semgrep,
    "bandit": parse_bandit,
    "pip-audit": parse_pip_audit,
    "npm-audit": parse_npm_audit,
    "gitleaks": parse_gitleaks,
    "trivy": parse_trivy,
    "zap-baseline": lambda folder: parse_zap(folder, "zap-baseline", "zap-baseline.json"),
    "zap-api": lambda folder: parse_zap(folder, "zap-api", "zap-api.json"),
    "schemathesis": parse_schemathesis,
    "nuclei": parse_nuclei,
    "cross-tenant": parse_cross_tenant,
    "testssl": parse_testssl,
    "observatory": parse_observatory,
}


def load_allowlist(path: str) -> list[AllowEntry]:
    entries = []
    if not path or not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8") as handle:
        for number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split(" | ", 3)]
            if len(parts) != 4 or not all(parts):
                raise SystemExit(f"{path}:{number}: needs 'tool | rule id | location | reason', each filled in")
            if parts[0] not in TOOLS:
                raise SystemExit(f"{path}:{number}: unknown tool {parts[0]!r}")
            entries.append(AllowEntry(*parts))
    return entries


def read_status(folder: str) -> dict[str, tuple[str, str]]:
    status: dict[str, tuple[str, str]] = {}
    try:
        with open(os.path.join(folder, "status.tsv"), encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    status[parts[0]] = (parts[1], parts[2] if len(parts) > 2 else "")
    except OSError:
        pass
    return status


def build_summary(folder: str, allowlist: list[AllowEntry], release: str) -> tuple[str, list[dict]]:
    status = read_status(folder)
    rows, decisions, record = [], [], []
    for tool in TOOLS:
        findings = PARSERS[tool](folder)
        kept, allowed = [], 0
        for finding in findings:
            entry = next((entry for entry in allowlist if entry.matches(finding)), None)
            record.append({**asdict(finding), "allow_listed": entry.reason if entry else None})
            if entry:
                allowed += 1
            else:
                kept.append(finding)
        state, note = status.get(tool, ("not run", ""))
        counts = {severity: sum(1 for f in kept if f.severity == severity) for severity in SEVERITIES}
        rows.append((tool, state, counts, allowed, note))
        for finding in kept:
            if finding.severity in ("Critical", "High") or (tool == "pip-audit" and finding.severity == "Unrated"):
                decisions.append(finding)

    lines = [
        f"# Security scan summary: {release}",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by scripts/security_scan_summary.py "
        "from the reports in this folder. Attack-style scans ran against the local test copy only.",
        "",
        "| Tool | Ran | " + " | ".join(SEVERITIES) + " | Allow-listed | Note |",
        "|---|---|" + "---|" * len(SEVERITIES) + "---|---|",
    ]
    for tool, state, counts, allowed, note in rows:
        cells = " | ".join(str(counts[s]) if state == "ran" else "-" for s in SEVERITIES)
        lines.append(
            f"| {tool} | {state} | {cells} | {allowed if state == 'ran' else '-'} | {note.replace('|', '/')} |"
        )
    lines += ["", "## Findings that need a decision (Critical, High, and unrated dependency advisories)", ""]
    if not decisions:
        lines.append("None.")
    grouped: dict[tuple[str, str, str], list[Finding]] = {}
    for finding in decisions:
        grouped.setdefault((finding.tool, finding.severity, finding.rule), []).append(finding)
    order = {severity: index for index, severity in enumerate(SEVERITIES)}
    for number, ((tool, severity, rule), items) in enumerate(
        sorted(grouped.items(), key=lambda kv: (order[kv[0][1]], kv[0][0], kv[0][2])), 1
    ):
        places = "; ".join(item.location for item in items[:3]) + (
            f"; +{len(items) - 3} more" if len(items) > 3 else ""
        )
        lines += [
            f"{number}. **{severity}** {tool} `{rule}`: {items[0].title}",
            f"   - Where: {places}",
            "   - Decision (fix now / fix later with date / false positive -> allow-list / accepted risk), by, date: ____",
        ]
    lines += [
        "",
        "Medium, Low and Info findings are in each tool's report and in findings.json; the deploy-blocking rules are in "
        "MDARIX-planning/security-scans/plan.md.",
    ]
    return "\n".join(lines) + "\n", record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", help="security-reports/<release>")
    parser.add_argument("--allowlist", default="infrastructure/security-scan/allowlist.txt")
    parser.add_argument("--release", default=None)
    args = parser.parse_args(argv)
    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print(f"No report folder {folder}", file=sys.stderr)
        return 2
    summary, record = build_summary(folder, load_allowlist(args.allowlist), args.release or os.path.basename(folder))
    with open(os.path.join(folder, "SUMMARY.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(summary)
    with open(os.path.join(folder, "findings.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
