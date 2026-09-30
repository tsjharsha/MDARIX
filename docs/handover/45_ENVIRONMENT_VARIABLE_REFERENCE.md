# Environment variable reference

Review `.env.example`, Compose files and settings modules for the authoritative names. Important groups include `MDARIX_ENV`, database URLs/roles, session/security settings, `MDARIX_GENAI_PROVIDER`, `MDARIX_GENAI_MODEL`, `MDARIX_GENAI_BASE_URL`, provider key, SMTP/Resend, object storage, data-plane registry and simulator tokens.

Values are environment-specific; placeholders are not proof of configuration. Keep secrets out of Git and rotate any key ever pasted into a shell or chat.
