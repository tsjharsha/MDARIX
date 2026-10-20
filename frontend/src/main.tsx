import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./app/App";
import { AppErrorBoundary } from "./app/ErrorBoundary";

// A website page arrives pre-rendered (scripts/prerender.mjs, WEB-05). createRoot, not hydrateRoot: the first render
// replaces that markup with the same page in one step. The pre-rendered copy is drawn without the browser's address,
// session or the data loaded at runtime (videos, legal texts, company details), so hydrating it would report
// mismatches and redo the render anyway.
createRoot(document.getElementById("root")!).render(
  <AppErrorBoundary>
    <App />
  </AppErrorBoundary>,
);
