import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DistributorBody, IntakeBody, LookAheadSection, RepresentativeBody } from "./sections/LookAhead";
import {
  LOOK_AHEAD_TABS,
  lookAheadTab,
  type DistributorPreview,
  type IntakePreview,
  type RepresentativePreview,
} from "./partyPreview";
import { TRIAL_ONLY_SECTIONS, WORKSPACE_SECTIONS } from "./workspaceContext";
import { GUIDE_SECTIONS } from "../help/userGuide";
import { TRIAL_TO_MVP } from "../help/trialNextSteps";

const BANNER =
  "Preview with sample data. In a pilot, your distributor or authorised representative signs in separately, with MFA and an access end date (from MDARIX 1.0.1).";
const PRRC = "The authorised representative is not your PRRC. It has its own PRRC (MDR Art. 11 and 15(6)).";
const frame = { banner: BANNER, read_only: true as const };

const intake: IntakePreview = {
  ...frame,
  page: "INTAKE",
  party: "Sample Distributor Europe (Sample)",
  submission: {
    reference: "DIST-REF-2231",
    product: "VentraLink 250 Respiratory Controller (Sample) Rev B",
    lot: "SAMPLE-VENTRA-250-LOT-004",
    first_knowledge: "2026-09-25",
    words: "Low-flow alarm right after a filter change.",
    becomes: "SAMPLE-RT-01",
  },
};
const distributor: DistributorPreview = {
  ...frame,
  page: "DISTRIBUTOR_STATUS",
  party: "Sample Distributor Europe (Sample)",
  statuses: [],
  items: [
    {
      reference: "DIST-REF-2231",
      complaint: "SAMPLE-RT-01",
      status: "CLOSED",
      status_label: "Closed",
      received: "2026-10-29",
      last_change: "2026-10-31",
      closing_note: "Closed at service level.",
    },
  ],
};
const representative: RepresentativePreview = {
  ...frame,
  page: "AUTHORISED_REPRESENTATIVE",
  party: "Sample EU Authorised Representative (Sample)",
  prrc_note: PRRC,
  products: ["OrbitCare 300 Infusion Pump (Sample)", "VentraLink 250 Respiratory Controller (Sample)"],
  complaints: [
    {
      id: "c-7",
      ref: "CMP000007",
      identifier: "SAMPLE-RV-07",
      product: "VentraLink 250 Respiratory Controller (Sample)",
      country: "France",
      status: "UNDER_ASSESSMENT",
      state: "Under assessment",
      received: "2026-10-19",
      last_change: "2026-10-31",
      eu_assessment: { state: "SIGNED", label: "Signed: reportable", date: "2026-10-31" },
    },
  ],
  high_risk: [
    {
      id: "c-7",
      ref: "CMP000007",
      identifier: "SAMPLE-RV-07",
      product: "VentraLink 250 Respiratory Controller (Sample)",
      country: "France",
      codes: ["REPORTABLE"],
      reasons: ["EU and Northern Ireland (EU MDR) concluded reportable"],
    },
  ],
  recurring: {
    signals: [
      {
        id: "s-1",
        ref: "SIG000001",
        title: "5 complaints: pressure alarm on OrbitCare 300",
        product: "OrbitCare 300 Infusion Pump (Sample)",
        complaints: 5,
        status: "INVESTIGATION_OPEN",
        last_event: "2026-10-25",
      },
    ],
    service_level: [],
    rule: "2 or more service-level resolutions on one product and problem code within 30 days that no open case covers",
  },
};

/** Every control a person could use: an input, textarea, select or button that is neither disabled nor read-only. */
const usable = (html: string) =>
  (html.match(/<(input|textarea|select|button)\b[^>]*>/g) ?? []).filter(
    (tag) => !/\sdisabled=""/.test(tag) && !/\sreadonly=""/i.test(tag),
  );

describe("the distributor and authorised-representative preview (T-G37P)", () => {
  it("is a trial-only section with three pages, in the story's order", () => {
    expect(WORKSPACE_SECTIONS).toContain("Look ahead");
    expect(TRIAL_ONLY_SECTIONS).toContain("Look ahead");
    expect(LOOK_AHEAD_TABS).toEqual([
      "How a distributor reports",
      "As your distributor sees it",
      "As your authorised representative sees it",
    ]);
    expect(lookAheadTab("As your distributor sees it")).toBe("As your distributor sees it");
    expect(lookAheadTab("nothing")).toBe("How a distributor reports");
    const html = renderToStaticMarkup(<LookAheadSection focus="As your authorised representative sees it" />);
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain("As your authorised representative sees it");
  });

  it("shows the intake form filled, with the banner, and nothing can be sent (TA-37P.3)", () => {
    const html = renderToStaticMarkup(<IntakeBody data={intake} />);
    expect(html).toContain(BANNER);
    expect(html).toContain("DIST-REF-2231");
    expect(html).toContain("Send to the manufacturer");
    expect(html).toContain("Preview: nothing is sent.");
    // Five fields, the reporter's words and the Send button are on the page, and none of them can be used.
    expect(html.match(/<(input|textarea|button)\b/g)).toHaveLength(7);
    expect(usable(html)).toEqual([]);
  });

  it("lists the distributor's complaints with status and the released closing note, and offers no control", () => {
    const html = renderToStaticMarkup(<DistributorBody data={distributor} />);
    expect(html).toContain(BANNER);
    expect(html).toContain("SAMPLE-RT-01");
    expect(html).toContain("Closed at service level.");
    expect(usable(html)).toEqual([]);
  });

  it("shows the authorised representative's products, both panels and the PRRC note, and offers no control", () => {
    const html = renderToStaticMarkup(<RepresentativeBody data={representative} />);
    expect(html).toContain(BANNER);
    expect(html).toContain(PRRC);
    expect(html).toContain("High risk (1)");
    expect(html).toContain("Recurring issues (1)");
    expect(html).toContain("5 complaints: pressure alarm on OrbitCare 300");
    expect(html).toContain("Signed: reportable");
    expect(html).not.toContain("PulseWatch");
    expect(usable(html)).toEqual([]);
  });

  it("says nothing to preview once the sample data is removed", () => {
    const empty = "The sample data was removed, so there is nothing to preview.";
    expect(renderToStaticMarkup(<IntakeBody data={{ ...intake, submission: null, empty }} />)).toContain(empty);
    expect(renderToStaticMarkup(<DistributorBody data={{ ...distributor, items: [], empty }} />)).toContain(empty);
    expect(renderToStaticMarkup(<RepresentativeBody data={{ ...representative, products: [], empty }} />)).toContain(
      empty,
    );
  });

  it("is in the user guide and in Next steps, with the pilot's 1.0.1 sign-in", () => {
    expect(GUIDE_SECTIONS.some((section) => section.id === "look-ahead")).toBe(true);
    const row = TRIAL_TO_MVP.find((item) => item.aspect.startsWith("Distributors"));
    expect(row?.trial).toContain("Look ahead");
    expect(row?.mvp).toContain("MFA and an access end date (from MDARIX 1.0.1)");
  });
});
