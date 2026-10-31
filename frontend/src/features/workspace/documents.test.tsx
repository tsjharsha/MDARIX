import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { CaseDocumentLinks, RowView } from "./sections/Documents";
import {
  clauseText,
  documentLink,
  generateBody,
  judgementProblem,
  parseDocumentLink,
  recordsText,
  signProblem,
  sourceTarget,
  versionsPath,
  type DocumentVersion,
  type Template,
} from "./documents";

const render = (node: ReactNode) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { allowed_menu: ["home"], business_permissions: ["quality.review", "data.export"] },
          open: vi.fn(),
          notify: vi.fn(),
          work: { setInvestigationId: vi.fn() },
        } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

const template = (scope: Template["scope"]): Template => ({
  code: scope === "ORGANIZATION" ? "MANAGEMENT_REVIEW" : scope === "CASE" ? "INVESTIGATION_REPORT" : "CHANGE_IMPACT",
  title: "A document",
  template_version: "mrr-starter-1",
  clauses: [],
  scope,
  purpose: "",
  judgements: [],
  starter_mark: "Starter text",
});

const version = (judgement: DocumentVersion["judgement"] = {}): DocumentVersion =>
  ({
    id: "v-1",
    version: 1,
    status: "DRAFT",
    editable: true,
    judgement,
    sections: [
      { key: "COMPLAINTS", title: "Feedback and complaint handling", kind: "data", rows: [] },
      { key: "ACTIONS_DECIDED", title: "Actions decided", kind: "judgement", prompt: "The actions." },
    ],
  }) as unknown as DocumentVersion;

describe("ready-to-use documents (T-G35)", () => {
  it("generates for a period, or for the case or change record chosen", () => {
    expect(generateBody(template("ORGANIZATION"), 90, "")).toEqual({ code: "MANAGEMENT_REVIEW", period_days: 90 });
    expect(generateBody(template("CASE"), 90, "")).toBeNull();
    expect(generateBody(template("CASE"), 90, "case-1")).toEqual({ code: "INVESTIGATION_REPORT", case_id: "case-1" });
    expect(generateBody(template("CHANGE"), 90, "chg-1")).toEqual({ code: "CHANGE_IMPACT", change_id: "chg-1" });
    expect(versionsPath("INVESTIGATION_REPORT", "case-1")).toBe(
      "/api/v1/documents?code=INVESTIGATION_REPORT&scope_id=case-1",
    );
  });

  it("prints each clause pending approval until it is confirmed (TA-35.5)", () => {
    const clause = { id: "ISO13485_5_6_2", short: "ISO 13485 5.6.2", title: "Management review input" };
    expect(clauseText({ ...clause, state: "pending approval" })).toBe(
      "ISO 13485 5.6.2 Management review input (pending approval)",
    );
    expect(clauseText({ ...clause, state: "confirmed" })).toBe("ISO 13485 5.6.2 Management review input");
  });

  it("signs only once every judgement section is written, with the password", () => {
    expect(judgementProblem("short")).toBe("Write at least 10 characters");
    expect(judgementProblem("Open an investigation into cable wear.")).toBeNull();
    expect(signProblem(version(), "secret")).toBe("Write Actions decided first");
    const written = version({ ACTIONS_DECIDED: { text: "Done in time.", written_by_name: "Priya", written_at: "" } });
    expect(signProblem(written, "")).toBe("Enter your password to sign");
    expect(signProblem(written, "secret")).toBeNull();
  });

  it("opens each source record where MDARIX shows it", () => {
    expect(sourceTarget({ type: "Disposition", id: "c-1", ref: "CMP000041 v1" })).toEqual({
      kind: "section",
      section: "Complaints",
      tab: "Dispositions",
    });
    expect(sourceTarget({ type: "Capa", id: "capa-1", ref: "CAPA000002" })).toEqual({
      kind: "section",
      section: "Records",
      tab: "Effectiveness checks?capa=capa-1",
    });
    expect(sourceTarget({ type: "CaseReview", id: "r-1", ref: "REV000001", case: "case-1" })).toEqual({
      kind: "case",
      caseId: "case-1",
      tab: "Reviews",
    });
    expect(sourceTarget({ type: "Change", id: "chg-1", ref: "SAMPLE-CHG-014" })).toBeNull();
  });

  it("shows a row's records behind a toggle, with how many it did not list", () => {
    const row = {
      text: "Resolved at service level: 3.",
      sources: [{ type: "Complaint", id: "c-1", ref: "CMP000041" }],
      more: 2,
    };
    expect(recordsText(row)).toBe("3 records");
    const html = render(<RowView row={row} />);
    expect(html).toContain("Resolved at service level: 3.");
    expect(html).toContain("<details");
    expect(html).toContain("CMP000041");
    expect(html).toContain("and 2 more");
  });

  it("links Readiness and the case page to Records › Reports with the document chosen", () => {
    expect(documentLink("MANAGEMENT_REVIEW")).toBe("Reports?doc=MANAGEMENT_REVIEW");
    expect(parseDocumentLink(documentLink("RISK_REVIEW_EXTRACT", "case-1"))).toEqual({
      code: "RISK_REVIEW_EXTRACT",
      scope: "case-1",
    });
    expect(parseDocumentLink("Reports")).toEqual({ code: null, scope: null });
    const html = render(<CaseDocumentLinks investigationId="case-1" />);
    expect(html).toContain("Investigation report");
    expect(html).toContain("Risk-review extract");
  });
});
