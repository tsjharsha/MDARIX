import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintsSection, SecondLookCard, SettingsBody } from "./sections/Complaints";
import { addressFor, locationFromAddress } from "./workspaceAddress";
import { VIEW_TO_SECTION } from "./UserWorkspace";
import { WORKSPACE_SECTIONS, sectionAllowed } from "./workspaceContext";
import { viewFromPath } from "../../app/router";
import type { ReviewSettings, SecondLookItem } from "./complaintReview";

/** The workspace the Complaints section needs; nothing here loads data (no effects run). */
function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["products", "investigations"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: {
      products: [],
      requestOpenInvestigation: vi.fn(),
    },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode, permissions: string[] = []) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const item = (overrides: Partial<SecondLookItem> = {}): SecondLookItem => ({
  id: "0b6f8f9e-1111-4222-8333-444455556666",
  business_id: "CMP000012",
  complaint_identifier: "SRC-12",
  product_id: "9d1c2b3a-1111-4222-8333-444455556666",
  product_name: "Infusion Pump",
  version: "B",
  status: "Cancelled",
  complaint_type: null,
  problem_code: null,
  severity: null,
  description: "Patient was choking on the tube",
  received_date: "2026-09-01",
  patient_involved: true,
  serious_injury: null,
  death: null,
  malfunction: null,
  reasons: [{ code: "CANCELLED", label: "Cancelled or rejected (status: Cancelled)" }],
  signs: [
    { code: "PATIENT_INVOLVED", label: "Patient involved" },
    { code: "WORDS", label: "Mentions choking" },
  ],
  words: ["choking"],
  score: 90,
  decision: null,
  ...overrides,
});

describe("the Complaints section", () => {
  it("offers the second look, the backlog and the settings, opening the tab a link names", () => {
    const tabs = (markup: string) => [...markup.matchAll(/role="tab"[^>]*>([^<]+)</g)].map((match) => match[1]);
    expect(tabs(render(<ComplaintsSection />))).toEqual(["Second look", "Backlog", "Review settings"]);
    expect(render(<ComplaintsSection />)).toContain("Checking your records");
    expect(render(<ComplaintsSection tab="Backlog" />)).toContain("Reading your open complaints");
    expect(render(<ComplaintsSection tab="Unknown" />)).toContain("Checking your records");
  });

  it("has its own address and menu entry", () => {
    expect(viewFromPath("/app/complaints")).toBe("complaints");
    expect(VIEW_TO_SECTION.complaints).toEqual(["Complaints"]);
    expect(addressFor({ section: "Complaints", tab: "Backlog" })).toBe("/app/complaints?tab=Backlog");
    expect(locationFromAddress("/app/complaints", "?tab=Backlog", VIEW_TO_SECTION, WORKSPACE_SECTIONS)).toEqual({
      section: "Complaints",
      tab: "Backlog",
    });
    expect(sectionAllowed("Complaints", ["products"])).toBe(true);
    expect(sectionAllowed("Complaints", ["audit"])).toBe(false);
  });
});

describe("a second-look card", () => {
  it("shows why the record is flagged, its signs and the matched words marked", () => {
    const markup = render(<SecondLookCard item={item()} onDecide={vi.fn()} />, ["investigation.create"]);
    expect(markup).toContain("CMP000012");
    expect(markup).toContain("Source ID SRC-12");
    expect(markup).toContain("Cancelled or rejected (status: Cancelled)");
    expect(markup).toContain("Patient involved");
    expect(markup).toContain("Patient was <mark>choking</mark> on the tube");
    expect(markup).toContain("uw-cr-rail tone-serious");
    expect(markup).toContain("It is a complaint");
    expect(markup).toContain("Not a complaint");
  });

  it("offers no decision to a role that may not decide", () => {
    const markup = render(<SecondLookCard item={item()} onDecide={vi.fn()} />, ["records.write"]);
    expect(markup).not.toContain("It is a complaint");
    expect(markup).not.toContain("Change decision");
  });

  it("shows a decision with who, why, a change and the next step", () => {
    const decided = item({
      decision: {
        decision: "CONFIRMED",
        reason: "Meets our complaint definition",
        decided_by: "Dana Quality",
        decided_at: "2026-10-01T09:00:00Z",
      },
    });
    const markup = render(<SecondLookCard item={decided} onDecide={vi.fn()} />, ["signal.triage", "records.write"]);
    expect(markup).toContain("Confirmed complaint");
    expect(markup).toContain("Dana Quality");
    expect(markup).toContain("Meets our complaint definition");
    expect(markup).toContain("Change decision");
    expect(markup).toContain("Open investigation");
    expect(markup).not.toContain("It is a complaint</button>");
  });
});

describe("the review settings", () => {
  const settings: ReviewSettings = {
    backlog_target_days: 14,
    second_look_words: ["discoloured"],
    custom_words: true,
    default_words: ["injury", "death"],
    version: 2,
    updated_by_name: "Tara Triage",
    updated_at: "2026-10-01T09:00:00Z",
  };

  it("lets a triage lead change them", () => {
    const markup = render(<SettingsBody settings={settings} onSaved={vi.fn()} />, ["signal.triage"]);
    expect(markup).toContain("14 days from receipt");
    expect(markup).toContain("Your organization&#x27;s 1 word");
    expect(markup).toContain("Tara Triage");
    expect(markup).toContain("Save settings");
  });

  it("shows them read-only to everyone else", () => {
    const markup = render(<SettingsBody settings={settings} onSaved={vi.fn()} />, ["investigation.create"]);
    expect(markup).not.toContain("Save settings");
    expect(markup).toContain("A triage lead can change these settings.");
    expect(markup).toContain("discoloured");
  });
});
