import { useState, type FormEvent } from "react";
import { CircleCheck } from "lucide-react";
import { AuthFrame } from "./AuthPage";

const FAILED = "Your request could not be sent. Please check your details and try again.";

// Request a demo: name, work email and phone. Same frame as sign-in and sign-up; MDARIX staff follow up.
export function RequestDemoPage() {
  const [form, setForm] = useState({ name: "", email: "", phone: "", website: "" });
  const [state, setState] = useState<{ status: "idle" | "sending" | "sent"; error?: string }>({ status: "idle" });
  const update = (field: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setState({ status: "sending" });
    try {
      const response = await fetch("/api/v1/public/demo-requests", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(form),
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => null))?.detail;
        setState({ status: "idle", error: typeof detail?.message === "string" ? detail.message : FAILED });
        return;
      }
      setState({ status: "sent" });
    } catch {
      setState({
        status: "idle",
        error: "Your request could not be sent. Please check your connection and try again.",
      });
    }
  };

  if (state.status === "sent") {
    const first = form.name.trim().split(/\s+/)[0];
    return (
      <AuthFrame mode="request-demo">
        <div className="auth-card auth-demo-done" role="status">
          <CircleCheck size={44} aria-hidden="true" />
          <span className="eyebrow">Request received</span>
          <h1>Thank you{first ? `, ${first}` : ""}.</h1>
          <p className="auth-lead">
            Someone from the MDARIX team will contact you shortly at <strong>{form.email.trim()}</strong> or{" "}
            <strong>{form.phone.trim()}</strong> to arrange your demo.
          </p>
          <p className="auth-links">
            <a href="/">Back to website</a> · <a href="/signup">Start free trial</a>
          </p>
        </div>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame mode="request-demo">
      <form className="auth-card" onSubmit={submit}>
        <span className="eyebrow">Request a demo</span>
        <h1>Book your demo</h1>
        <p className="auth-lead">
          Leave your details and someone from the MDARIX team will contact you to arrange a live demo.
        </p>
        <label className="auth-field">
          Full name
          <input name="name" autoComplete="name" required maxLength={120} value={form.name} onChange={update("name")} />
        </label>
        <label className="auth-field">
          Work email
          <input
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            value={form.email}
            onChange={update("email")}
          />
        </label>
        <label className="auth-field">
          Phone number
          <input
            name="phone"
            type="tel"
            autoComplete="tel"
            required
            minLength={7}
            maxLength={30}
            pattern={"\\+?[0-9 \\(\\)\\.\\-]{7,30}"}
            title="Digits, spaces and + ( ) - . only, for example +1 617 555 0100"
            placeholder="e.g. +1 617 555 0100"
            value={form.phone}
            onChange={update("phone")}
          />
        </label>
        {/* Left empty by people; filled only by automated form fillers. */}
        <div className="auth-demo-trap" aria-hidden="true">
          <input name="website" tabIndex={-1} autoComplete="off" value={form.website} onChange={update("website")} />
        </div>
        {state.error && (
          <p className="auth-demo-error" role="alert">
            {state.error}
          </p>
        )}
        <button className="primary-action" type="submit" disabled={state.status === "sending"}>
          {state.status === "sending" ? "Sending…" : "Request a demo"}
        </button>
        <p className="auth-consent">
          We use these details only to arrange your demo, as described in our <a href="/privacy">Privacy Policy</a>.
        </p>
        <p className="auth-links auth-links-split">
          <span>
            Explore on your own? <a href="/signup">Start free trial</a>
          </span>
        </p>
      </form>
    </AuthFrame>
  );
}
