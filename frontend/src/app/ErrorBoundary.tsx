import React from "react";
import { AlertTriangle } from "lucide-react";
import { lastFailedRequestId, requestJson } from "./apiClient";

export type ClientErrorReport = {
  path: string;
  message: string;
  stack?: string;
  component?: string;
  request_id?: string;
};

/**
 * What is sent about a screen that crashed: the page address (without its query, which can carry search terms),
 * the error and where it happened. Never the contents of forms or the data on screen.
 */
export function clientErrorReport(
  error: unknown,
  component: string | undefined,
  location: { pathname: string },
  requestId?: string,
): ClientErrorReport {
  const raw = error instanceof Error ? error : new Error(String(error));
  return {
    path: (location.pathname || "/").slice(0, 512),
    message: (raw.message || raw.name || "Unknown error").slice(0, 1000),
    ...(raw.stack ? { stack: raw.stack.slice(0, 20_000) } : {}),
    ...(component ? { component: component.slice(0, 200) } : {}),
    ...(requestId && requestId.length <= 64 ? { request_id: requestId } : {}),
  };
}

/** Best effort: a report that cannot be delivered is dropped, never retried in a loop or shown to the person. */
export function reportClientError(error: unknown, component?: string) {
  const body = clientErrorReport(error, component, window.location, lastFailedRequestId());
  void requestJson("/api/v1/client-errors", {
    method: "POST",
    body: JSON.stringify(body),
    retries: 0,
    timeoutMs: 10_000,
    redirectOnUnauthorized: false,
  }).catch(() => undefined);
}

type Props = { children: React.ReactNode };
type State = { failed: boolean };

/** The last line of defence for the whole application: a full-page message instead of a blank page. */
export class AppErrorBoundary extends React.Component<Props, State> {
  state: State = { failed: false };
  static getDerivedStateFromError(): State {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("MDARIX frontend error", error);
    reportClientError(error, firstComponent(info) ?? "App");
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="auth-shell" role="alert">
        <section className="auth-card">
          <span className="eyebrow">MDARIX secure application</span>
          <h1>Something went wrong</h1>
          <p>The page could not be loaded safely. Refresh the page or return to the home screen.</p>
          <button className="primary-action" onClick={() => window.location.reload()}>
            Refresh
          </button>
        </section>
      </main>
    );
  }
}

const firstComponent = (info: React.ErrorInfo) =>
  info.componentStack
    ?.split("\n")
    .map((line) => /at (\w+)/.exec(line)?.[1] ?? /^\s*(\w+)@/.exec(line)?.[1])
    .find(Boolean);

type SectionProps = {
  /** The section's name, shown to the person and sent with the report. */
  name: string;
  /** Changing it (opening another section) clears the failure, so the rest of the app keeps working. */
  resetKey?: unknown;
  children: React.ReactNode;
};
type SectionState = { failed: boolean; resetKey?: unknown };

/**
 * Keeps one broken section from blanking the application: the navigation and every other section stay usable,
 * the person sees what failed and can try again, and the error is reported to MDARIX.
 */
export class SectionErrorBoundary extends React.Component<SectionProps, SectionState> {
  state: SectionState = { failed: false, resetKey: this.props.resetKey };
  static getDerivedStateFromError(): Partial<SectionState> {
    return { failed: true };
  }
  static getDerivedStateFromProps(props: SectionProps, state: SectionState): Partial<SectionState> | null {
    return props.resetKey !== state.resetKey ? { failed: false, resetKey: props.resetKey } : null;
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`MDARIX section error (${this.props.name})`, error);
    reportClientError(error, `${this.props.name}${firstComponent(info) ? ` · ${firstComponent(info)}` : ""}`);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="ac-panel section-error" role="alert">
        <div className="ac-empty tone-critical-text">
          <AlertTriangle size={22} aria-hidden="true" />
          <strong>{this.props.name} could not be shown</strong>
          <span>
            Something went wrong on this page. The rest of MDARIX still works, and the problem has been reported. Try
            again, or open another section.
          </span>
          <button type="button" className="ac-secondary" onClick={() => this.setState({ failed: false })}>
            Try again
          </button>
        </div>
      </section>
    );
  }
}
