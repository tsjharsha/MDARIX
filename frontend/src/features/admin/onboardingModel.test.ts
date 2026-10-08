import { describe, expect, it } from "vitest";
import {
  EMPTY_FORM,
  REVIEW_STEP,
  eligiblePlans,
  formFromDraft,
  invitationText,
  provisionPayload,
  reachableStep,
  stepProblems,
  suggestTenantCode,
  type OnboardingForm,
} from "./onboardingModel";

const complete: OnboardingForm = {
  ...EMPTY_FORM,
  company_name: "Acme Medical",
  tenant_code: "ACME_MEDICAL",
  region: "UK",
  plan_code: "STARTER",
  customer_admin_email: "Ada@Acme.example",
  customer_admin_display_name: "Ada Admin",
  reason: "Signed contract 2026-114",
};

describe("new-customer wizard", () => {
  it("offers only active plans with customer administration, never the free trial", () => {
    const plans = eligiblePlans([
      { code: "STARTER", status: "ACTIVE", capabilities: { ADMIN_CONTROL_PLANE: true } },
      { code: "FREE_TRIAL", status: "ACTIVE", capabilities: { ADMIN_CONTROL_PLANE: true } },
      { code: "DEMO", status: "ACTIVE", capabilities: { ASK_MDARIX: true } },
      { code: "OLD", status: "RETIRED", capabilities: { ADMIN_CONTROL_PLANE: true } },
    ]);
    expect(plans.map((plan) => plan.code)).toEqual(["STARTER"]);
  });

  it("suggests a tenant code from the company name", () => {
    expect(suggestTenantCode("Acme Medical Devices, Inc.")).toBe("ACME_MEDICAL_DEVICES_INC");
    expect(suggestTenantCode("  Øresund — Health  ")).toBe("ORESUND_HEALTH");
  });

  it("checks each step before the next one opens", () => {
    expect(stepProblems(1, EMPTY_FORM)).toHaveLength(1);
    expect(stepProblems(2, { ...complete, tenant_code: "a" })).toHaveLength(1);
    expect(stepProblems(4, complete, ["PROFESSIONAL"])).toEqual(["Choose a plan."]);
    expect(stepProblems(4, { ...complete, licensed_users_limit: Number.NaN }, ["STARTER"])).toHaveLength(1);
    expect(stepProblems(6, { ...complete, customer_admin_email: "not-an-email" })).toHaveLength(1);
    expect(stepProblems(REVIEW_STEP, { ...complete, reason: "short" })).toHaveLength(1);
    expect(reachableStep(EMPTY_FORM, ["STARTER"])).toBe(1);
    expect(reachableStep(complete, ["STARTER"])).toBe(REVIEW_STEP);
  });

  it("sends one region for processing and residency, and tidies the details", () => {
    const payload = provisionPayload({ ...complete, tenant_code: "acme_medical" });
    expect(payload).toMatchObject({
      tenant_code: "ACME_MEDICAL",
      region: "UK",
      residency: "UK",
      customer_admin_email: "ada@acme.example",
      customer_admin_company: "Acme Medical",
      customer_reference: null,
      reason: "Signed contract 2026-114",
    });
  });

  it("restores a draft from the earlier wizard, keeping only known fields", () => {
    const form = formFromDraft({
      company_name: "Acme",
      domain: "CRM-7",
      identity_provider: "Okta",
      licensed_users_limit: "x",
    });
    expect(form.company_name).toBe("Acme");
    expect(form.customer_reference).toBe("CRM-7");
    expect(form.licensed_users_limit).toBe(EMPTY_FORM.licensed_users_limit);
    expect(form).not.toHaveProperty("identity_provider");
  });

  it("explains the administrator's invitation", () => {
    expect(invitationText("SENT", "a@b.example")).toBe("Invitation email sent to a@b.example.");
    expect(invitationText("CREATED", "a@b.example")).toContain("email is not set up on this server");
  });
});
