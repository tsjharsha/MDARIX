import { describe, expect, it } from "vitest";
import {
  backlogAgeText,
  backlogHeadline,
  backlogPath,
  backlogStateOf,
  bandSlices,
  decisionBody,
  decisionProblem,
  decisionText,
  highlightParts,
  otherDecision,
  reasonSlices,
  recordId,
  recordTone,
  secondLookHeadline,
  secondLookPath,
  settingsBody,
  settingsChanged,
  settingsForm,
  settingsProblem,
  signTone,
  targetShare,
  wordsOf,
  type ReviewSettings,
} from "./complaintReview";

const marked = (text: string, words: string[]) =>
  highlightParts(text, words)
    .filter((part) => part.match)
    .map((part) => part.text);

describe("the second look", () => {
  it("asks the server for open or decided records, by product when one is chosen", () => {
    expect(secondLookPath("open", "", 1)).toBe("/api/v1/complaints/second-look?state=open&page=1&page_size=25");
    expect(secondLookPath("decided", "p-1", 3, 10)).toBe(
      "/api/v1/complaints/second-look?state=decided&page=3&page_size=10&product_id=p-1",
    );
  });

  it("tones harm above everything else, and a card by its most serious sign", () => {
    expect(signTone("DEATH")).toBe("critical");
    expect(signTone("SERIOUS_INJURY")).toBe("critical");
    expect(signTone("MALFUNCTION")).toBe("serious");
    expect(signTone("SEVERITY")).toBe("warning");
    expect(signTone("WORDS")).toBe("neutral");
    expect(recordTone([])).toBe("neutral");
    expect(
      recordTone([
        { code: "WORDS", label: "Mentions pain" },
        { code: "DEATH", label: "Death reported" },
        { code: "MALFUNCTION", label: "Malfunction" },
      ]),
    ).toBe("critical");
  });

  it("marks the matched words as whole words, any case, across separators", () => {
    expect(marked("Patient had SHORTNESS-OF-BREATH; the casing was painted", ["shortness of breath", "pain"])).toEqual([
      "SHORTNESS-OF-BREATH",
    ]);
    expect(marked("Choking. choking again", ["choking"])).toEqual(["Choking", "choking"]);
    // The longer phrase wins over a word inside it.
    expect(marked("Error code E12 shown", ["error", "error code"])).toEqual(["Error code"]);
    expect(marked("Ünder pain", ["pain"])).toEqual(["pain"]);
    expect(marked("Spain", ["pain"])).toEqual([]);
    // Words with regular-expression characters are taken literally.
    expect(marked("Reading (high) was shown", ["(high)"])).toEqual(["(high)"]);
  });

  it("keeps every character of the description in order", () => {
    const text = "Pump stopped working, error code E12 and an alarm";
    const parts = highlightParts(text, ["stopped working", "alarm"]);
    expect(parts.map((part) => part.text).join("")).toBe(text);
    expect(highlightParts("", ["alarm"])).toEqual([]);
    expect(highlightParts("No words", [])).toEqual([{ text: "No words", match: false }]);
  });

  it("says how many records may be hidden complaints, harm first", () => {
    const none = secondLookHeadline({ to_review: 0, with_harm: 0, confirmed: 2, dismissed: 1, by_reason: {} });
    expect(none.tone).toBe("good");
    expect(none.title).toBe("Nothing waits for a second look");
    const harm = secondLookHeadline({ to_review: 5, with_harm: 1, confirmed: 0, dismissed: 0, by_reason: {} });
    expect(harm).toMatchObject({ title: "5 records may be hidden complaints", tone: "critical" });
    expect(harm.detail).toContain("1 record reports a death or a serious injury");
    const one = secondLookHeadline({ to_review: 1, with_harm: 0, confirmed: 0, dismissed: 0, by_reason: {} });
    expect(one).toMatchObject({ title: "1 record may be a hidden complaint", tone: "warning" });
  });

  it("lists the three reasons with their counts, zero when missing", () => {
    expect(reasonSlices({ CANCELLED: 2, NFF_RECURRING: 3 }).map((slice) => [slice.key, slice.count])).toEqual([
      ["CANCELLED", 2],
      ["INQUIRY", 0],
      ["NFF_RECURRING", 3],
    ]);
    expect(reasonSlices(null).every((slice) => slice.count === 0)).toBe(true);
  });

  it("asks for a reason of at least 10 characters and sends it tidied", () => {
    expect(decisionProblem("   short   ")).toBe("Say in at least 10 characters why");
    expect(decisionProblem("x".repeat(2001))).toBe("Keep the reason under 2000 characters");
    expect(decisionProblem("Meets our complaint definition")).toBeNull();
    expect(decisionBody("DISMISSED", "  A duplicate   of CMP000123 ")).toEqual({
      decision: "DISMISSED",
      reason: "A duplicate of CMP000123",
    });
  });

  it("names decisions and offers the other one when revising", () => {
    expect(decisionText("CONFIRMED")?.badge).toBe("Confirmed complaint");
    expect(decisionText("DISMISSED")?.action).toBe("Not a complaint");
    expect(decisionText("MAYBE")).toBeNull();
    expect(otherDecision("CONFIRMED")).toBe("DISMISSED");
    expect(otherDecision("DISMISSED")).toBe("CONFIRMED");
    expect(otherDecision(undefined)).toBe("CONFIRMED");
  });

  it("names a record by its MDARIX ID, else its source number", () => {
    expect(recordId({ business_id: "CMP000012", complaint_identifier: "SRC-1" })).toBe("CMP000012");
    expect(recordId({ business_id: null, complaint_identifier: "SRC-1" })).toBe("SRC-1");
    expect(recordId({ business_id: null, complaint_identifier: null })).toBe("Complaint");
  });
});

describe("the backlog board", () => {
  it("asks the server for all, past-target or due-soon complaints", () => {
    expect(backlogPath("past_target", "", 2)).toBe("/api/v1/complaints/backlog?show=past_target&page=2&page_size=25");
    expect(backlogPath("all", "p-9", 1)).toContain("&product_id=p-9");
  });

  it("reads each state with a label and a tone, never colour alone", () => {
    expect(backlogStateOf("PAST_TARGET")).toEqual({ label: "Past target", tone: "critical" });
    expect(backlogStateOf("DUE_SOON")).toEqual({ label: "Due soon", tone: "warning" });
    expect(backlogStateOf("ON_TRACK")).toEqual({ label: "On track", tone: "good" });
    expect(backlogStateOf("ODD")).toEqual({ label: "—", tone: "neutral" });
  });

  it("says a complaint's age against the target", () => {
    expect(backlogAgeText(40, 30)).toBe("40 days · 10 days past target");
    expect(backlogAgeText(31, 30)).toBe("31 days · 1 day past target");
    expect(backlogAgeText(26, 30)).toBe("26 days · 4 days left");
    expect(backlogAgeText(30, 30)).toBe("30 days · due today");
    expect(backlogAgeText(0, 30)).toBe("Received today · 30 days left");
    expect(backlogAgeText(null, 30)).toBe("Date not recorded");
  });

  it("fills the age meter up to the target and no further", () => {
    expect(targetShare(15, 30)).toBe(50);
    expect(targetShare(90, 30)).toBe(100);
    expect(targetShare(null, 30)).toBe(0);
    expect(targetShare(5, 0)).toBe(0);
  });

  it("tones the age bands against the target", () => {
    const bands = [
      { band: "0-30", count: 2 },
      { band: "31-60", count: 1 },
      { band: "61-90", count: 0 },
      { band: "90+", count: 4 },
    ];
    expect(bandSlices(bands, 30).map((slice) => [slice.label, slice.tone])).toEqual([
      ["0–30 days", "good"],
      ["31–60 days", "critical"],
      ["61–90 days", "critical"],
      ["90+ days", "critical"],
    ]);
    expect(bandSlices(bands, 45).map((slice) => slice.tone)).toEqual(["good", "warning", "critical", "critical"]);
    expect(bandSlices(null, 30)).toEqual([]);
  });

  it("leads with what is past the target, then what is due soon", () => {
    const base = { target_days: 30, on_track: 0, oldest_days: 40, bands: [] };
    expect(backlogHeadline({ ...base, open_unlinked: 0, past_target: 0, due_soon: 0 }).tone).toBe("good");
    const past = backlogHeadline({ ...base, open_unlinked: 3, past_target: 1, due_soon: 1 });
    expect(past).toMatchObject({ title: "1 complaint past the 30-day target", tone: "critical" });
    expect(past.detail).toContain("3 open complaints are in no signal and no case; 1 more is due within a week");
    expect(backlogHeadline({ ...base, open_unlinked: 2, past_target: 0, due_soon: 2 })).toMatchObject({
      title: "2 complaints due within a week",
      tone: "warning",
    });
    expect(backlogHeadline({ ...base, open_unlinked: 1, past_target: 0, due_soon: 0, on_track: 1 }).tone).toBe("good");
  });
});

describe("the review settings", () => {
  const defaults = ["injury", "death", "alarm"];
  const settings = (overrides: Partial<ReviewSettings> = {}): ReviewSettings => ({
    backlog_target_days: 30,
    second_look_words: defaults,
    custom_words: false,
    default_words: defaults,
    version: 0,
    updated_by_name: null,
    updated_at: null,
    ...overrides,
  });

  it("reads the word list one per line or comma separated, tidied and without repeats", () => {
    expect(wordsOf(" Choking ,choking\n\nShort   of breath\n")).toEqual(["choking", "short of breath"]);
    expect(wordsOf("")).toEqual([]);
  });

  it("sees no change in the defaults, or in a custom list equal to them", () => {
    const current = settings();
    const form = settingsForm(current);
    expect(form).toEqual({ targetDays: "30", words: "injury\ndeath\nalarm", useDefaults: true, reason: "" });
    expect(settingsChanged(current, form)).toBe(false);
    expect(settingsChanged(current, { ...form, useDefaults: false })).toBe(false);
    expect(settingsChanged(current, { ...form, targetDays: "20" })).toBe(true);
    expect(settingsChanged(current, { ...form, useDefaults: false, words: "discoloured" })).toBe(true);
  });

  it("sees going back to the defaults, and a different custom list, as changes", () => {
    const custom = settings({ second_look_words: ["discoloured"], custom_words: true, version: 1 });
    const form = settingsForm(custom);
    expect(form.useDefaults).toBe(false);
    expect(settingsChanged(custom, form)).toBe(false);
    expect(settingsChanged(custom, { ...form, useDefaults: true })).toBe(true);
    expect(settingsChanged(custom, { ...form, words: "discoloured\ncracked" })).toBe(true);
  });

  it("checks the target, the words and the reason before sending", () => {
    const form = { targetDays: "30", words: "discoloured", useDefaults: false, reason: "Our procedure says 30 days" };
    expect(settingsProblem(form)).toBeNull();
    expect(settingsProblem({ ...form, targetDays: "0" })).toBe("The target is a whole number of days from 1 to 365");
    expect(settingsProblem({ ...form, targetDays: "12.5" })).toBe("The target is a whole number of days from 1 to 365");
    expect(settingsProblem({ ...form, words: " \n " })).toBe("Keep at least one word, or use the default words");
    expect(settingsProblem({ ...form, words: Array.from({ length: 101 }, (_, i) => `w${i}`).join("\n") })).toBe(
      "Keep at most 100 words",
    );
    expect(settingsProblem({ ...form, words: "x".repeat(61) })).toContain("is longer than 60 characters");
    expect(settingsProblem({ ...form, useDefaults: true, words: "" })).toBeNull();
    expect(settingsProblem({ ...form, reason: "too short" })).toBe("Say in at least 10 characters why");
  });

  it("sends null words for the defaults", () => {
    expect(settingsBody({ targetDays: "14", words: "x", useDefaults: true, reason: " Back to  defaults " })).toEqual({
      backlog_target_days: 14,
      second_look_words: null,
      reason: "Back to defaults",
    });
    expect(
      settingsBody({ targetDays: "30", words: "Discoloured\ncracked", useDefaults: false, reason: "Our own words" }),
    ).toMatchObject({ second_look_words: ["discoloured", "cracked"] });
  });
});
