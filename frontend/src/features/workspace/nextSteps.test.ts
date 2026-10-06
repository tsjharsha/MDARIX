import { describe, expect, it } from "vitest";
import {
  emptyNextStep,
  nextStepBody,
  nextStepForm,
  nextStepOptions,
  nextStepOptionsPath,
  nextStepProblem,
  nextStepResultText,
  nextStepsPath,
  type NextStepInput,
} from "./nextSteps";

const today = "2026-10-06";
const reason = "Lot test data is still missing for KS-5521.";

describe("next step options", () => {
  it("reads the server's options, a list or an object holding them", () => {
    const options = nextStepOptions([
      { action: "CONTINUE_INVESTIGATION", label: "Continue the investigation", available: true },
      { action: "request_risk_review", available: false, reason: "A risk review is already open" },
      { label: "No action" },
    ]);
    expect(options).toEqual([
      {
        action: "CONTINUE_INVESTIGATION",
        label: "Continue the investigation",
        description: null,
        available: true,
        reason: null,
      },
      {
        action: "REQUEST_RISK_REVIEW",
        label: "Request Risk Review",
        description: null,
        available: false,
        reason: "A risk review is already open",
      },
    ]);
    expect(nextStepOptions({ items: [{ action: "NO_DECISION_YET" }] })).toHaveLength(1);
    expect(nextStepOptions({ options: [{ action: "NO_DECISION_YET" }] })).toHaveLength(1);
    expect(nextStepOptions(null)).toEqual([]);
  });

  it("opens the right form for each step", () => {
    expect(nextStepForm("CONTINUE_INVESTIGATION")).toBe("reason");
    expect(nextStepForm("NO_DECISION_YET")).toBe("reason");
    expect(nextStepForm("REQUEST_RISK_REVIEW")).toBe("review");
    expect(nextStepForm("REQUEST_REGULATORY_REVIEW")).toBe("review");
    expect(nextStepForm("REQUEST_ADDITIONAL_EVIDENCE")).toBe("request");
    expect(nextStepForm("REQUEST_ADDITIONAL_TESTING")).toBe("request");
    expect(nextStepForm("REVIEW_SUPPLIER_CHANGE")).toBe("change");
    expect(nextStepForm("REVIEW_PRODUCT_CHANGE")).toBe("change");
    expect(nextStepForm("ESCALATE_FOR_QUALITY_REVIEW")).toBe("brief");
    expect(nextStepForm("SOMETHING_NEW")).toBe("reason");
  });

  it("addresses the options and the step", () => {
    expect(nextStepOptionsPath("i 1")).toBe("/api/v1/investigations/i%201/next-steps/options");
    expect(nextStepsPath("i1")).toBe("/api/v1/investigations/i1/next-steps");
  });
});

describe("a step's form", () => {
  it("asks a reason of 10 to 2000 characters for every step", () => {
    expect(nextStepProblem("CONTINUE_INVESTIGATION", emptyNextStep(), today)).toMatch(/at least 10/);
    expect(nextStepProblem("CONTINUE_INVESTIGATION", { ...emptyNextStep(), reason }, today)).toBeNull();
    expect(nextStepProblem("NO_DECISION_YET", { ...emptyNextStep(), reason: "x".repeat(2001) }, today)).toMatch(/2000/);
    expect(nextStepBody("NO_DECISION_YET", { ...emptyNextStep(), reason: ` ${reason} ` })).toEqual({
      action: "NO_DECISION_YET",
      reason,
    });
  });

  it("never records an escalation here: it goes through the Decision Brief", () => {
    expect(nextStepProblem("ESCALATE_FOR_QUALITY_REVIEW", { ...emptyNextStep(), reason }, today)).toMatch(
      /Decision Brief/,
    );
  });

  it("asks for an evidence or test request like the New request drawer, to a person or a role queue", () => {
    const input: NextStepInput = { ...emptyNextStep(), reason };
    expect(nextStepProblem("REQUEST_ADDITIONAL_TESTING", input, today)).toMatch(/at least 3/);
    const filled: NextStepInput = {
      ...input,
      request: {
        ...input.request,
        title: "Seal hardness tests",
        items: "Shore A hardness\n\nCompression set",
        recipientMode: "role",
        recipientRole: "INVESTIGATOR",
        dueDay: "2026-10-20",
        priority: "HIGH",
        unknownId: "u-1",
      },
    };
    expect(nextStepProblem("REQUEST_ADDITIONAL_TESTING", filled, today)).toBeNull();
    expect(
      nextStepProblem(
        "REQUEST_ADDITIONAL_TESTING",
        { ...filled, request: { ...filled.request, dueDay: "2026-10-01" } },
        today,
      ),
    ).toMatch(/past/);
    const body = nextStepBody("REQUEST_ADDITIONAL_TESTING", filled);
    expect(body).toMatchObject({
      action: "REQUEST_ADDITIONAL_TESTING",
      reason,
      details: {
        title: "Seal hardness tests",
        requested_items: ["Shore A hardness", "Compression set"],
        recipient_role: "INVESTIGATOR",
        priority: "HIGH",
        unknown_id: "u-1",
      },
    });
    expect((body as { details: Record<string, unknown> }).details.due_at).toEqual(expect.any(String));
    expect((body as { details: Record<string, unknown> }).details).not.toHaveProperty("recipient_user_id");
    const person = nextStepBody("REQUEST_ADDITIONAL_EVIDENCE", {
      ...filled,
      request: { ...filled.request, recipientMode: "person", recipientUserId: "user-1", dueDay: "", unknownId: "" },
    }) as { details: Record<string, unknown> };
    expect(person.details).toMatchObject({ recipient_user_id: "user-1" });
    expect(person.details).not.toHaveProperty("recipient_role");
    expect(person.details).not.toHaveProperty("due_at");
    expect(person.details).not.toHaveProperty("unknown_id");
  });

  it("assigns a change review to a person or role only when one is chosen", () => {
    const input: NextStepInput = { ...emptyNextStep(), reason };
    expect(nextStepProblem("REVIEW_SUPPLIER_CHANGE", input, today)).toBeNull();
    expect(nextStepBody("REVIEW_SUPPLIER_CHANGE", input)).toEqual({ action: "REVIEW_SUPPLIER_CHANGE", reason });
    const person = { ...input, change: { ...input.change, mode: "person" as const } };
    expect(nextStepProblem("REVIEW_PRODUCT_CHANGE", person, today)).toMatch(/person/);
    expect(
      nextStepBody("REVIEW_PRODUCT_CHANGE", {
        ...input,
        change: { mode: "role", assigneeUserId: "ignored", assignedRole: "REVIEWER", title: " Release C seal " },
      }),
    ).toEqual({
      action: "REVIEW_PRODUCT_CHANGE",
      reason,
      details: { assigned_role: "REVIEWER", title: "Release C seal" },
    });
  });
});

describe("a step's result", () => {
  it("names what the step created by business ID", () => {
    expect(nextStepResultText("Request risk review", { result: { review: { business_id: "REV000003" } } })).toBe(
      "Request risk review recorded: REV000003.",
    );
    expect(nextStepResultText("Continue", { result: { business_id: "TSK000010" } })).toBe(
      "Continue recorded: TSK000010.",
    );
    expect(nextStepResultText("Continue", { result: { id: "0b6f8f9e-1111-4222-8333-444455556666" } })).toBe(
      "Continue recorded.",
    );
    expect(nextStepResultText("Continue", null)).toBe("Continue recorded.");
  });
});
