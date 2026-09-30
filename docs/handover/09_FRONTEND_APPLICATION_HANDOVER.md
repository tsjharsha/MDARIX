# Frontend application handover

The frontend is a React/Vite application with a public website, authenticated Platform Admin, Customer Admin, Mapping Studio and investigation/evidence/AI surfaces. Navigation is route-aware in `frontend/src/main.tsx`; styles are shared through `frontend/src/styles.css` and admin-specific CSS.

Maintain role-specific route resolution before rendering to avoid stale menu flashes. Preserve tenant scoping in API calls and clear cached data on tenant changes. Remaining quality work includes continued component extraction, specialized cards where generic tables remain, authenticated browser evidence and full screen-reader review.
