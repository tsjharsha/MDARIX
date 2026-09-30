# Troubleshooting guide

Common failures: port already in use (inspect the owning process); database authentication/SSL mismatch (verify container, role, password and PGSSLMODE); stale frontend bundle (restart Vite and hard refresh); provider unavailable (check configured model/key and deterministic fallback); Playwright browser timeout (use installed browser/cache or rerun with network access). Record the cause and environment.
