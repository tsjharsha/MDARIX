import { describe, expect, it } from "vitest";

import {
  COMPANY_SIZES,
  COMPLAINT_SYSTEMS,
  COMPLAINT_VOLUMES,
  DEVICE_CLASSES,
  EMPTY_PROFILE,
  MARKETS,
  TRIAL_DATA,
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
