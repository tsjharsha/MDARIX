# MDARIX frontend MVP architecture

MDARIX intentionally remains a React/Vite application for the current MVP.
The route registry in `frontend/src/app/router.ts` is the single source of
truth for protected and public application paths; the route test verifies that
every declared view round-trips through the registry. Navigation policy remains
server-authorized at the API boundary.

Shared UI primitives are in `frontend/src/app/ui.tsx` and the design tokens are
in `frontend/src/styles.css`. Feature modules are under
`frontend/src/features/`; the existing `main.tsx` is being reduced gradually to
shell orchestration and compatibility page composition rather than replaced by
a risky framework migration during MVP.

The current local validation passed 13 frontend tests and a production Vite
build. The build emits a chunk-size warning for future code splitting; it is
not a functional failure.

Next.js migration is therefore deferred, not required for the React/Vite MVP.
Desktop/mobile screenshots, full keyboard evidence, NVDA review, and complete
authenticated route walkthroughs require a live browser session and are
evidence activities rather than source-code changes.
