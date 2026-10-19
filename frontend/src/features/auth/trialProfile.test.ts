import { describe, expect, it } from "vitest";

import {
  COMPANY_SIZES,
  COMPLAINT_SYSTEMS,
  COMPLAINT_VOLUMES,
  DEVICE_CLASSES,
  EMPTY_PROFILE,
  MARKETS,
  TRIAL_DATA,
  isPersonalEmail,
  signupBody,
  toggleMarket,
} from "./trialProfile";

describe("trial request profile", () => {
  it("sends every answer under the name the server reads, and never a password", () => {
    const body = signupBody("qa@example.com", "Asha Rao", "Acme Devices", {
      ...EMPTY_PROFILE,
      jobTitle: "Director of Quality",
      country: "India",
      markets: ["US", "EU"],
      complaintSystem: "TRACKWISE",
      noPatientData: true,
    });
    expect(body).toMatchObject({
      email: "qa@example.com",
      display_name: "Asha Rao",
      organization: "Acme Devices",
      job_title: "Director of Quality",
      country: "India",
      markets: ["US", "EU"],
      complaint_system: "TRACKWISE",
      no_patient_data: true,
    });
    expect(body).not.toHaveProperty("password");
  });

  it("adds and removes markets", () => {
    expect(toggleMarket([], "US")).toEqual(["US"]);
    expect(toggleMarket(["US", "EU"], "US")).toEqual(["EU"]);
  });

  it("offers the codes backend/app/trial/request_profile.py accepts", () => {
    const codes = (options: { value: string }[]) => options.map((option) => option.value);
    expect(codes(COMPANY_SIZES)).toEqual(["1-50", "51-200", "201-1000", "1001-5000", "5000+"]);
    expect(codes(DEVICE_CLASSES)).toEqual(["CLASS_I", "CLASS_II", "CLASS_III", "IVD", "NOT_SURE"]);
    expect(codes(MARKETS)).toEqual(["US", "EU", "UK", "CA", "IN", "OTHER"]);
    expect(codes(COMPLAINT_SYSTEMS)).toEqual([
      "TRACKWISE",
      "VEEVA_QMS",
      "MASTERCONTROL",
      "GREENLIGHT_GURU",
      "ETQ",
      "SAP",
      "SALESFORCE",
      "SPREADSHEETS",
      "OTHER",
    ]);
    expect(codes(COMPLAINT_VOLUMES)).toEqual(["LT_50", "50_500", "501_5000", "GT_5000", "NOT_SURE"]);
    expect(codes(TRIAL_DATA)).toEqual(["SAMPLE_ONLY", "ANONYMIZED_EXPORTS"]);
  });
});

describe("country and phone", () => {
  it("lists every country by name, sorted, with its dialing code kept for the phone", async () => {
    const { countries } = await import("./trialProfile");
    const list = countries();
    expect(list.length).toBeGreaterThan(240);
    const byCode = Object.fromEntries(list.map((country) => [country.code, country]));
    expect(byCode.IN).toMatchObject({ name: "India", dial: "+91", label: "India" });
    expect(list.some((country) => country.label.includes("+"))).toBe(false);
    expect(byCode.US.dial).toBe("+1");
    expect(byCode.GB.dial).toBe("+44");
    expect(byCode.DE.dial).toBe("+49");
    const names = list.map((country) => country.name);
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, "en")));
  });

  it("accepts phones in international format only, and an empty phone", async () => {
    const { isInternationalPhone } = await import("./trialProfile");
    expect(isInternationalPhone("")).toBe(true);
    expect(isInternationalPhone("+91 98765 43210")).toBe(true);
    expect(isInternationalPhone("+1 (555) 010-0199")).toBe(true);
    expect(isInternationalPhone("98765 43210")).toBe(false);
    expect(isInternationalPhone("+0 123 456 789")).toBe(false);
    expect(isInternationalPhone("+12345")).toBe(false);
    expect(isInternationalPhone("+91 98765 43210 12345")).toBe(false);
  });

  it("keeps the phone optional after a country is chosen: the dialling code alone is no phone", async () => {
    const { isInternationalPhone, phoneWithDialCode, signupBody } = await import("./trialProfile");
    const phone = phoneWithDialCode("", "+91"); // what choosing India puts in the field
    expect(isInternationalPhone(phone)).toBe(true);
    expect(isInternationalPhone("+1")).toBe(true);
    const profile = { phone } as Parameters<typeof signupBody>[3];
    expect(signupBody("qa@example.com", "Asha Rao", "Acme Devices", profile).phone).toBe("");
    expect(
      signupBody("qa@example.com", "Asha Rao", "Acme Devices", { ...profile, phone: " +91 98765 43210 " }).phone,
    ).toBe("+91 98765 43210");
  });

  it("starts the phone with the chosen country's code, without overwriting a typed number", async () => {
    const { phoneWithDialCode } = await import("./trialProfile");
    expect(phoneWithDialCode("", "+91")).toBe("+91 ");
    expect(phoneWithDialCode("+44", "+91")).toBe("+91 ");
    expect(phoneWithDialCode("+44 20 7946 0958", "+91")).toBe("+44 20 7946 0958");
  });
});

describe("personal email addresses", () => {
  it("are recognised by the server's free-mail list, including its subdomains, and only once the list is known", () => {
    const list = ["gmail.com", "yahoo.co.in", "outlook.com"];
    expect(isPersonalEmail("asha@gmail.com", list)).toBe(true);
    expect(isPersonalEmail("  Asha@GMAIL.com ", list)).toBe(true);
    expect(isPersonalEmail("asha@mail.yahoo.co.in", list)).toBe(true);
    expect(isPersonalEmail("asha@acme-devices.com", list)).toBe(false);
    expect(isPersonalEmail("asha@notgmail.com", list)).toBe(false);
    expect(isPersonalEmail("asha@", list)).toBe(false);
    expect(isPersonalEmail("asha@gmail.com", undefined)).toBe(false);
  });
});
