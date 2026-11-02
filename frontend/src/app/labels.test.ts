import { describe, expect, it } from "vitest";
import { codeWords, marketLabel, questionNumber, triggerLabel, versionWords, zoneLabel } from "./labels";

describe("names, not codes (J18)", () => {
  it("says every code in words", () => {
    expect(marketLabel("EU_NI")).toBe("EU and Northern Ireland");
    expect(marketLabel("IN")).toBe("India");
    expect(triggerLabel("NEW_FAILURE_MODE")).toBe("New failure mode");
    expect(triggerLabel("RECURRENCE")).toBe("Recurrence no case covers");
    expect(codeWords("COMPLAINT_THRESHOLD")).toBe("Complaint threshold");
    expect(versionWords("disposition-starter-1")).toBe("MDARIX starter, version 1");
    expect(versionWords("response-starter-1")).toBe("MDARIX starter, version 1");
    expect(versionWords("US-v2")).toBe("your version 2");
    expect(versionWords("Version 1.2")).toBe("Version 1.2");
    expect(questionNumber("US2A")).toBe("2a");
    expect(questionNumber("EU_NI3")).toBe("3");
    expect(zoneLabel("Asia/Calcutta")).toBe(zoneLabel("Asia/Kolkata"));
    expect(zoneLabel("America/New_York")).toBe("America / New York");
  });
});
