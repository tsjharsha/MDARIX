/**
 * What a trial requester tells MDARIX about their company and trial. The codes are the ones
 * backend/app/trial/request_profile.py accepts. No password is asked for: the requester creates it from the
 * invitation email after approval, and MDARIX staff never see it.
 */

import { DIALING_CODES } from "./dialingCodes";

export type Option = { value: string; label: string };

export const COMPANY_SIZES: Option[] = [
  { value: "1-50", label: "1-50 employees" },
  { value: "51-200", label: "51-200 employees" },
  { value: "201-1000", label: "201-1,000 employees" },
  { value: "1001-5000", label: "1,001-5,000 employees" },
  { value: "5000+", label: "More than 5,000 employees" },
];

export const DEVICE_CLASSES: Option[] = [
  { value: "CLASS_I", label: "Class I" },
  { value: "CLASS_II", label: "Class II" },
  { value: "CLASS_III", label: "Class III" },
  { value: "IVD", label: "In vitro diagnostic (IVD)" },
  { value: "NOT_SURE", label: "Not sure" },
];

export const MARKETS: Option[] = [
  { value: "US", label: "United States (FDA)" },
  { value: "EU", label: "European Union (MDR/IVDR)" },
  { value: "UK", label: "United Kingdom" },
  { value: "CA", label: "Canada" },
  { value: "IN", label: "India" },
  { value: "OTHER", label: "Other" },
];

export const COMPLAINT_SYSTEMS: Option[] = [
  { value: "TRACKWISE", label: "TrackWise" },
  { value: "VEEVA_QMS", label: "Veeva QMS" },
  { value: "MASTERCONTROL", label: "MasterControl" },
  { value: "GREENLIGHT_GURU", label: "Greenlight Guru" },
  { value: "ETQ", label: "ETQ Reliance" },
  { value: "SAP", label: "SAP" },
  { value: "SALESFORCE", label: "Salesforce" },
  { value: "SPREADSHEETS", label: "Spreadsheets or email" },
  { value: "OTHER", label: "Other" },
];

export const COMPLAINT_VOLUMES: Option[] = [
  { value: "LT_50", label: "Fewer than 50 a month" },
  { value: "50_500", label: "50-500 a month" },
  { value: "501_5000", label: "501-5,000 a month" },
  { value: "GT_5000", label: "More than 5,000 a month" },
  { value: "NOT_SURE", label: "Not sure" },
];

export const TRIAL_DATA: Option[] = [
  { value: "SAMPLE_ONLY", label: "Sample data only" },
  { value: "ANONYMIZED_EXPORTS", label: "Our anonymized exports" },
];

export type TrialProfile = {
  jobTitle: string;
  country: string;
  phone: string;
  companySize: string;
  deviceTypes: string;
  deviceClass: string;
  markets: string[];
  complaintSystem: string;
  complaintVolume: string;
  trialData: string;
  evaluationGoal: string;
  noPatientData: boolean;
};

export const EMPTY_PROFILE: TrialProfile = {
  jobTitle: "",
  country: "",
  phone: "",
  companySize: "",
  deviceTypes: "",
  deviceClass: "",
  markets: [],
  complaintSystem: "",
  complaintVolume: "",
  trialData: "",
  evaluationGoal: "",
  noPatientData: false,
};

/** Adds the market when it is not chosen yet, removes it when it is. */
export function toggleMarket(markets: string[], code: string): string[] {
  return markets.includes(code) ? markets.filter((item) => item !== code) : [...markets, code];
}

/** The body of POST /api/v1/auth/signup. Empty optional answers are sent empty and stored as not given. */
export function signupBody(email: string, name: string, company: string, profile: TrialProfile) {
  return {
    email,
    display_name: name,
    organization: company,
    job_title: profile.jobTitle,
    country: profile.country,
    phone: profile.phone,
    company_size: profile.companySize,
    device_types: profile.deviceTypes,
    device_class: profile.deviceClass,
    markets: profile.markets,
    complaint_system: profile.complaintSystem,
    complaint_volume: profile.complaintVolume,
    trial_data: profile.trialData,
    evaluation_goal: profile.evaluationGoal,
    no_patient_data: profile.noPatientData,
  };
}

export type Country = { code: string; name: string; dial: string; label: string };

/**
 * Every country and territory for the sign-up dropdown, sorted and shown by name ("India"), with its dialing code
 * from libphonenumber's metadata (dialingCodes.ts) to start the phone number; the name is the browser's standard English
 * region name.
 */
export function countries(locale = "en"): Country[] {
  const names =
    typeof Intl !== "undefined" && "DisplayNames" in Intl ? new Intl.DisplayNames([locale], { type: "region" }) : null;
  return DIALING_CODES.map(([code, dial]) => {
    const name = names?.of(code) ?? code;
    return { code, name, dial, label: name };
  }).sort((a, b) => a.name.localeCompare(b.name, locale));
}

/** The same check the server makes (backend/app/trial/request_profile.py): +, the country code, then 8 to 15 digits in
 * all; an empty phone is fine (it is optional). */
export function isInternationalPhone(value: string): boolean {
  const phone = value.trim();
  if (!phone) return true;
  const digits = phone.replace(/\D/g, "").length;
  return /^\+[1-9][0-9 ().-]*$/.test(phone) && digits >= 8 && digits <= 15;
}

/** When a country is chosen and the phone is still empty (or only another country's code), start it with the code. */
export function phoneWithDialCode(phone: string, dial: string): string {
  const current = phone.trim();
  return !current || /^\+\d{1,4}$/.test(current) ? `${dial} ` : phone;
}
