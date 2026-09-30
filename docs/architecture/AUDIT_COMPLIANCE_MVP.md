# Audit and compliance MVP

Audit events remain tenant-scoped, redacted, append-only by policy, and carry
seven-year retention timestamps. The hash-chain contract adds `previous_hash`
and `event_hash` to make tampering detectable; verification reports the exact
failed event positions.

The existing evidence-package endpoint produces a tenant-scoped downloadable
ZIP with redacted audit CSV/manifest data. Standard audit construction captures
request IP/user-agent and changed old/new values through the shared helper.

External compliance gates remain separate: WORM/Object Lock storage,
certificate-backed signatures, browser evidence, operational archival, and a
formal 21 CFR Part 11 validation package require controlled infrastructure,
approved certificates, and validation protocols.
