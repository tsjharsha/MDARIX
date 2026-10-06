"""Investigation evidence (Phase 3): what a case holds as evidence, how it is judged, and how more is asked for.

- ``rules``: review statuses, relationships, request statuses and their labels, request validation and the actions a
  person may take (no database).
- ``people``: the signed-in person as these endpoints see them (permissions, roles) and the any-of permission check.
- ``inventory``: ``/api/v1/investigations/{id}/evidence-inventory``, ``/evidence-links``, ``/evidence/{id}/review``
  and ``/evidence/{id}/provenance``.
- ``requests``: ``/api/v1/investigations/{id}/evidence-requests`` and ``/api/v1/evidence-requests`` (requests to a
  colleague or a role, and to suppliers through the existing supplier request flow), their attachments and their
  review into evidence.
- ``hooks``: what those actions do to workflow tasks; never blocking (backend/app/workflow/tasks.run_hook).
"""
