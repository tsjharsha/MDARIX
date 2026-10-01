import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./app/App";
import { AppErrorBoundary } from "./app/ErrorBoundary";

createRoot(document.getElementById("root")!).render(
  <AppErrorBoundary>
    <App />
  </AppErrorBoundary>,
);
