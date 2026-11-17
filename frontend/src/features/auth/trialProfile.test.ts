import { describe, expect, it } from "vitest";

import {
  COMPANY_SIZES,
  COMPLAINT_SYSTEMS,
  COMPLAINT_VOLUMES,
  DEVICE_CLASSES,
  EMPTY_PROFILE,
  MARKETS,
  TRIAL_DATA,
  mailKind,
  reviewedFirst,
  signupBody,
  toggleMarket,
  trialApproval,
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

  it("names a territory the browser has no name for, never its bare code (G-21)", async () => {
    const { countries } = await import("./trialProfile");
    const real = Intl.DisplayNames;
    class Bare {
      of(code: string) {
        return code === "EH" ? "EH" : new real(["en"], { type: "region" }).of(code);
      }
    }
    (Intl as { DisplayNames: unknown }).DisplayNames = Bare;
    try {
      const western = countries().find((country) => country.code === "EH");
      expect(western?.name).toBe("Western Sahara");
    } finally {
      (Intl as { DisplayNames: unknown }).DisplayNames = real;
    }
  });

  it("leaves out the countries under comprehensive sanctions", async () => {
    const { countries } = await import("./trialProfile");
    const list = countries();
    for (const code of ["CU", "IR", "KP", "SY"]) expect(list.some((country) => country.code === code)).toBe(false);
    for (const name of ["Cuba", "Iran", "North Korea", "Syria", "Crimea"])
      expect(list.some((country) => country.name.includes(name))).toBe(false);
    // Neighbours and similarly named countries stay.
    for (const code of ["UA", "KR", "IQ", "RU"]) expect(list.some((country) => country.code === code)).toBe(true);
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

describe("company, personal and disposable email addresses", () => {
  const rules = {
    auto_approval: "company-and-personal",
    personal_mail_domains: ["gmail.com", "yahoo.co.in", "outlook.com"],
    disposable_mail_domains: ["mailinator.com", "yopmail.com"],
  };

  it("are told apart by the server's own lists, including their subdomains, and only once the lists are known", () => {
    expect(mailKind("asha@gmail.com", rules)).toBe("personal");
    expect(mailKind("  Asha@GMAIL.com ", rules)).toBe("personal");
    expect(mailKind("asha@mail.yahoo.co.in", rules)).toBe("personal");
    expect(mailKind("asha@mailinator.com", rules)).toBe("disposable");
    expect(mailKind("asha@inbox.yopmail.com", rules)).toBe("disposable");
    expect(mailKind("asha@acme-devices.com", rules)).toBe("company");
    expect(mailKind("asha@notgmail.com", rules)).toBe("company");
    expect(mailKind("asha@", rules)).toBe("company");
    expect(mailKind("asha@gmail.com", undefined)).toBe("company");
  });

  it("read the server's setting, and its default while it is not known", () => {
    expect(trialApproval(undefined)).toBe("company-and-personal");
    expect(trialApproval({})).toBe("company-and-personal");
    expect(trialApproval(rules)).toBe("company-and-personal");
    expect(trialApproval({ auto_approval: "company-domains" })).toBe("company-domains");
    expect(trialApproval({ auto_approval: "off" })).toBe("off");
  });

  it("are reviewed first as the server decides it", () => {
    // The default: a personal address is approved at once like a company one; a disposable one always waits.
    expect(reviewedFirst("company", "company-and-personal")).toBe(false);
    expect(reviewedFirst("personal", "company-and-personal")).toBe(false);
    expect(reviewedFirst("disposable", "company-and-personal")).toBe(true);
    // company-domains: as before 0.10.48, a personal address waits.
    expect(reviewedFirst("company", "company-domains")).toBe(false);
    expect(reviewedFirst("personal", "company-domains")).toBe(true);
    expect(reviewedFirst("disposable", "company-domains")).toBe(true);
    for (const kind of ["company", "personal", "disposable"] as const) expect(reviewedFirst(kind, "off")).toBe(true);
  });
});
