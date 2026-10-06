"""Post-market signals and triage (``/api/v1/triage``): groups of related complaints that a person triages,
prioritises and dispositions, and from which investigations are opened.

- ``labels``: statuses, origins, dispositions, event types and their labels; the detection rule and its defaults.
- ``logic``: the rules without a database (problem key, suggested priority, due dates, grouping, dispositions).
- ``service``: reading and changing signals in the tenant's data plane (history, audit, tasks, serialization).
- ``detection``: the complaint threshold rule, run per organization (scheduler, imports, the API, a script).
- ``hooks``: what other actions do to signals (imports, a signed decision, closing a case); never blocking.
- ``router``: the API.
The tables are in backend/app/db/models/signals.py (migration md28).
"""
