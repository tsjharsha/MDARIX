"""Trust and audit of one case (Phase 7): a merged, chronological timeline of everything recorded about it, a replay
of the case as it was known at a moment (by default when its decision was signed), the AI runs it used, the
integrity of its signatures, brief fingerprints and audit chain, and an audited export of all three. Read-only: the
only thing written is the CASE_AUDIT_EXPORTED audit event of an export. The pure rules (merge, deduplication, titles,
"known then" partitioning, statuses as of a moment) are in ``rules``; the readers in ``service``; the routes in
``router``.
"""
