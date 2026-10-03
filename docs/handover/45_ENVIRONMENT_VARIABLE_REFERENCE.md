# Environment variable reference

The complete, maintained list is [docs/runbooks/ENVIRONMENT_VARIABLES.md](../runbooks/ENVIRONMENT_VARIABLES.md):
every variable the server code reads, whether staging and production require it, and what it does. The test
`tests/test_environment_reference.py` fails when code reads a variable the reference does not list, and when the
production template (`.env.production.example`) lacks a required one.

Values are environment-specific; placeholders are not proof of configuration. Keep secrets out of Git and rotate any
key ever pasted into a shell, ticket or chat.
