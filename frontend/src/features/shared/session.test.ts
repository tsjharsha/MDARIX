import { describe, expect, it } from "vitest";
import { IDLE_SIGN_OUT_MS, SESSION_WARNING_MS, afterActivity, sessionDeadlines, sessionStep } from "./session";

const NOW = Date.parse("2026-10-05T10:00:00Z");
const minutes = (count: number) => count * 60 * 1000;

describe("session deadlines", () => {
  it("uses the server's idle_expires_at and expires_at when the session answer has them", () => {
    const deadlines = sessionDeadlines(
      { idle_expires_at: "2026-10-05T10:30:00Z", expires_at: "2026-10-05T21:00:00Z" },
      NOW,
    );
    expect(deadlines.endsAt).toBe(NOW + minutes(30));
    expect(deadlines.absoluteAt).toBe(Date.parse("2026-10-05T21:00:00Z"));
    expect(deadlines.idleWindowMs).toBe(minutes(30));
  });

  it("falls back to the configured 30 minutes when the fields are absent", () => {
    const deadlines = sessionDeadlines({}, NOW);
    expect(deadlines.endsAt).toBe(NOW + IDLE_SIGN_OUT_MS);
    expect(deadlines.absoluteAt).toBe(Number.POSITIVE_INFINITY);
    expect(sessionDeadlines(null, NOW).endsAt).toBe(NOW + IDLE_SIGN_OUT_MS);
  });

  it("ends at the absolute limit when it comes before the idle timeout", () => {
    const deadlines = sessionDeadlines(
      { idle_expires_at: "2026-10-05T10:30:00Z", expires_at: "2026-10-05T10:10:00Z" },
      NOW,
    );
    expect(deadlines.endsAt).toBe(NOW + minutes(10));
  });

  it("restarts the idle window on each server request, never past the absolute limit", () => {
    const deadlines = sessionDeadlines(
      { idle_expires_at: "2026-10-05T10:30:00Z", expires_at: "2026-10-05T10:45:00Z" },
      NOW,
    );
    expect(afterActivity(deadlines, NOW + minutes(5)).endsAt).toBe(NOW + minutes(35));
    expect(afterActivity(deadlines, NOW + minutes(20)).endsAt).toBe(NOW + minutes(45));
  });
});

describe("session watch steps", () => {
  const endsAt = NOW + minutes(30);
  it("waits until two minutes before the end", () => {
    expect(sessionStep(endsAt - SESSION_WARNING_MS - 1000, endsAt, false)).toBe("wait");
  });
  it("warns someone who has been away, and renews quietly for someone who is working", () => {
    expect(sessionStep(endsAt - 60_000, endsAt, false)).toBe("warn");
    expect(sessionStep(endsAt - 60_000, endsAt, true)).toBe("renew");
  });
  it("signs out at the end", () => {
    expect(sessionStep(endsAt, endsAt, true)).toBe("end");
  });
});
