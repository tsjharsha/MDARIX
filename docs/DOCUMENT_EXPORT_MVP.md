# MDARIX document export (MVP)

## Supported governed formats

The report service supports tenant-scoped JSON, CSV, PDF, Word-compatible DOC,
and an `ESTAR_XML` handoff envelope. Every export includes a report version,
tenant identifier, generated timestamp, human-review flag, and a controlled-copy
watermark. Hidden fields are removed before rendering, so they are absent from
the export payload rather than merely hidden in the UI.

Large exports use the durable `ReportJob` queue. Jobs are claimed with row
locking, retried, written below a tenant-specific temporary directory, and can
be downloaded only through the tenant-filtered job endpoint. Queue, download,
and compliance-report operations create audit events.

## Regulatory boundary

`ESTAR_XML` is an internal, provenance-preserving handoff envelope. It is not
FDA eSTAR schema validation and must not be submitted to FDA. Official FDA
eSTAR XML/PDF schemas and versioned templates must be supplied and pinned before
that gate can be closed. Notified Body technical-file templates likewise
require the partner's approved template and document-control rules. The PDF
renderer is a deterministic MVP renderer, not a pixel-perfect regulatory
template.

## Validation

`tests/test_compliance_report.py` verifies JSON/CSV/PDF plus Word and XML
outputs, watermarking, report versioning, and hidden-field removal. The
authenticated API adds `WORD`, `DOC`, and `ESTAR_XML` to the compliance report
and background-job endpoints.
