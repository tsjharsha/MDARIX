/*
 * Names, not codes (J18, V2): one label map per kind of code the server sends, so no screen shows NEW_FAILURE_MODE,
 * EU_NI, US2A or disposition-starter-1. A code the map does not know is still shown in words ("Complaint threshold").
 */

/** A code in words, sentence case: "COMPLAINT_THRESHOLD" -> "Complaint threshold". */
export const codeWords = (code: string | null | undefined): string => {
  const text = String(code ?? "")
    .trim()
    .replace(/[_-]+/g, " ")
    .toLowerCase();
  return text ? text[0].toUpperCase() + text.slice(1) : "";
};

const MARKETS: Record<string, string> = {
  US: "United States",
  EU_NI: "EU and Northern Ireland",
  EU: "European Union",
  GB: "Great Britain",
  IN: "India",
};

/** A market by its name: "EU_NI" -> "EU and Northern Ireland". */
export const marketLabel = (code: string | null | undefined): string =>
  code ? (MARKETS[code] ?? codeWords(code)) : "—";

// The escalation triggers' names (backend/app/complaint_disposition/triggers.py LABELS).
const TRIGGERS: Record<string, string> = {
  SAFETY: "Safety issue",
  INJURY: "Injury",
  REPORTABLE: "Reportable outcome",
  RECURRENCE: "Recurrence no investigation covers",
  NEW_FAILURE_MODE: "New failure mode",
};

/** An escalation trigger by its name: "NEW_FAILURE_MODE" -> "New failure mode". */
export const triggerLabel = (code: string): string => TRIGGERS[code] ?? codeWords(code);

/**
 * A document version in words, as the server says it (backend/app/standards.py version_words): "MDARIX starter,
 * version 1" for disposition-starter-1, "your version 2" for US-v2; any other version (a form's "Version 1.2") as it is.
 */
export const versionWords = (code: string | null | undefined): string => {
  const value = String(code ?? "").trim();
  const starter = /^.+-starter-(\d+)$/.exec(value);
  if (starter) return `MDARIX starter, version ${starter[1]}`;
  const own = /^.+-v(\d+)$/.exec(value);
  return own ? `your version ${own[1]}` : value || "—";
};

/** A decision guide question's number without its market's code: "US2A" -> "2a", "EU_NI3" -> "3". */
export const questionNumber = (id: string): string => id.replace(/^[A-Z_]*?(?=\d)/, "").toLowerCase() || id;

/** A time zone as a person reads it: "Asia/Kolkata" -> "Asia / Kolkata"; the old name Asia/Calcutta reads the same. */
export const zoneLabel = (zone: string): string =>
  (zone === "Asia/Calcutta" ? "Asia/Kolkata" : zone).replace(/_/g, " ").replace("/", " / ");
