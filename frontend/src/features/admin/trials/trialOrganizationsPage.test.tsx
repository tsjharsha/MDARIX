import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DOMAINS } from "../consoleDomains";
import { IDENTITY_SECTIONS, MOVED_SECTIONS, TRIAL_SECTIONS, movedTarget, sectionMatches } from "../areas/sections";
import { trialTileDetail } from "../console/AdminOverview";
import { TrialDetailView, eventLabel } from "./TrialDetail";
import { EndingAndDeletion, TrialRequests } from "./TrialOrganizations";
import { RunDeletionNow } from "./RunDeletion";
import {
  convertiblePlans,
  daysLeftText,
  extensionError,
  extensionSentence,
  nameMatches,
  reasonError,
  type TrialDetail,
} from "./model";

// TO-1: one Platform Admin area holds every free-trial link, and only those; the customer areas no longer list trials.

const trial = (changes: Partial<TrialDetail> = {}): TrialDetail => ({
  tenant_id: "t-1",
  tenant_business_id: "TEN000042",
  tenant_key: "TRIAL_ORBITCARE",
  name: "OrbitCare Devices",
  status: "ACTIVE",
  state: "ACTIVE",
  legal_hold: false,
  plan: "Free Trial",
  dates: {
    starts_at: "2026-11-01T09:00:00+00:00",
    ends_at: "2026-12-01T09:00:00+00:00",
    ends_words: "1 Dec 2026, 14:30 IST",
    days_left: 17,
    original_ends_at: "2026-12-01T09:00:00+00:00",
    latest_end: "2026-12-31T09:00:00+00:00",
    extension_used: 0,
    extension_left: 30,
    extension_max: 30,
    deletion: null,
  },
  people: {
    used: 2,
    owner: { id: "u1", email: "owner@orbitcare.example", name: "Taylor Quality", status: "ACTIVE" },
    people: [{ id: "u1", email: "owner@orbitcare.example", name: "Taylor Quality", status: "ACTIVE" }],
    request_email: "owner@orbitcare.example",
  },
  sample: {
    status: "LOADED",
    at: null,
    sample_only: false,
    sample_counts: { products: 3, complaints: 44 },
    own_counts: {},
    uploaded_rows: 0,
  },
  activity: { story: { acted_count: 2, total: 8, last_activity: null }, feedback: null, demo_request: null },
  exit_request: null,
  conversion: null,
  next_step: "Ends in 17 days: keep in touch.",
  actions: {
    extend: { allowed: true, reason: null, days_left: 30 },
    end: { allowed: true, reason: null, pending_request_id: null },
    convert: { allowed: true, reason: null },
    delete_data: { allowed: false, reason: "Not due yet: the data is deleted 30 days after the trial ends" },
  },
  ai: { enabled: false, line: "AI is off for free trials (trial terms)." },
  ...changes,
});

const render = (detail: TrialDetail) =>
  renderToStaticMarkup(<TrialDetailView detail={detail} history={[]} onAction={() => undefined} />);

describe("navigation", () => {
  it("puts Trial organizations right after Customers & Tenants, with its four sections", () => {
    const names = DOMAINS.map((domain) => domain[0]);
    expect(names.indexOf("Trial organizations")).toBe(names.indexOf("Customers & Tenants") + 1);
    const area = DOMAINS.find((domain) => domain[0] === "Trial organizations");
    expect(area?.[3]).toEqual(["Requests", "Trials", "Ending and deletion", "Feedback"]);
    expect([...TRIAL_SECTIONS]).toEqual(["Requests", "Trials", "Ending and deletion", "Feedback"]);
  });

  it("leaves no trial section in Customers & Tenants and no Onboarding in Identity & Access", () => {
    const customers = DOMAINS.find((domain) => domain[0] === "Customers & Tenants");
    expect(customers?.[3]).toEqual(["Customers", "Tenants"]);
    expect(IDENTITY_SECTIONS as readonly string[]).not.toContain("Onboarding");
  });

  it("opens old links in their new sections", () => {
    expect(movedTarget("Customers & Tenants", "Trials")).toEqual({ domain: "Trial organizations", item: "Trials" });
    expect(movedTarget("Customers & Tenants", "Feedback")).toEqual({ domain: "Trial organizations", item: "Feedback" });
    expect(movedTarget("Identity & Access", "Onboarding")).toEqual({ domain: "Trial organizations", item: "Requests" });
    expect(movedTarget("Trials")).toEqual({ domain: "Trial organizations", item: "Trials" });
    expect(movedTarget("Customers & Tenants", "Tenants")).toEqual({ domain: "Customers & Tenants", item: "Tenants" });
    for (const target of Object.values(MOVED_SECTIONS))
      expect(TRIAL_SECTIONS as readonly string[]).toContain(target.item);
  });

  it("finds the trial page by what is done there", () => {
    const description = "Free-trial requests, trials and how they end";
    for (const term of ["trial", "extend", "convert"])
      expect(sectionMatches(term, "Trial organizations", description, "Trials"), term).toBe(true);
    expect(sectionMatches("extend", "Customers & Tenants", "Customer and tenant lifecycle", "Tenants")).toBe(false);
  });
});

describe("trial detail", () => {
  it("shows dates, people, sample data, the next step and the AI line", () => {
    const html = render(trial());
    expect(html).toContain("OrbitCare Devices");
    expect(html).toContain("17 days left");
    expect(html).toContain("0 of 30 days used");
    expect(html).toContain("Taylor Quality");
    expect(html).toContain("Loaded");
    expect(html).toContain("Ends in 17 days: keep in touch.");
    expect(html).toContain("AI is off for free trials");
  });

  it("enables only the actions the server allows, with the reason for the others", () => {
    const html = render(trial());
    expect(html).toMatch(/<button[^>]*>(<svg[^]*?<\/svg>)? Extend<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>(<svg[^]*?<\/svg>)? Delete data now<\/button>/);
    expect(html).toContain("Not due yet: the data is deleted 30 days after the trial ends");
    const ended = render(
      trial({
        state: "ENDED_EARLY",
        actions: {
          extend: { allowed: false, reason: "A trial ended early cannot be extended" },
          end: { allowed: false, reason: "The trial has already ended" },
          convert: { allowed: true, reason: null },
          delete_data: { allowed: false, reason: "Not due yet" },
        },
      }),
    );
    expect(ended).toMatch(/<button[^>]*disabled=""[^>]*>(<svg[^]*?<\/svg>)? Extend<\/button>/);
    expect(ended).toContain("A trial ended early cannot be extended");
    expect(ended).toContain("Ended early");
  });

  it("offers Open in Customers on a converted trial only", () => {
    const converted = renderToStaticMarkup(
      <TrialDetailView
        detail={trial({ state: "CONVERTED", plan: null })}
        history={[]}
        onAction={() => undefined}
        onOpenCustomers={() => undefined}
      />,
    );
    expect(converted).toContain("Open in Customers");
    expect(
      renderToStaticMarkup(
        <TrialDetailView detail={trial()} history={[]} onAction={() => undefined} onOpenCustomers={() => undefined} />,
      ),
    ).not.toContain("Open in Customers");
  });

  it("words audit events plainly", () => {
    expect(eventLabel("TRIAL_EXTENDED")).toBe("Trial extended");
    expect(eventLabel("TRIAL_EXIT_RAISED_BY_MDARIX")).toBe("Ended by MDARIX");
    expect(eventLabel("SOMETHING_NEW")).toBe("Something new");
  });
});

describe("action drawers", () => {
  it("shows the days left of 30 and refuses more", () => {
    expect(extensionError(5, 30)).toBeNull();
    expect(extensionError(31, 30)).toContain("30 more days at most (30 in total)");
    expect(extensionError(5, 4)).toContain("4 more days at most");
    expect(extensionError(0, 30)).toContain("at least 1 day");
    const sentence = extensionSentence("2026-12-01T00:00:00Z", 12, 3, (date) => date.toISOString().slice(0, 10));
    expect(sentence).toBe("The trial will end on 2026-12-04. 15 of 30 extension days used.");
  });

  it("never offers the Free Trial plan for a conversion", () => {
    const plans = [
      { id: "1", code: "FREE_TRIAL", name: "Free Trial", status: "ACTIVE" },
      { id: "2", code: "PILOT", name: "Pilot", status: "ACTIVE" },
      { id: "3", code: "OLD", name: "Old", status: "RETIRED" },
    ];
    expect(convertiblePlans(plans).map((plan) => plan.code)).toEqual(["PILOT"]);
  });

  it("needs the organization's name typed and a reason of 10 characters", () => {
    expect(nameMatches("orbitcare  devices", "OrbitCare Devices")).toBe(true);
    expect(nameMatches("OrbitCare", "OrbitCare Devices")).toBe(false);
    expect(nameMatches("", "")).toBe(false);
    expect(reasonError("short")).toContain("10 characters");
    expect(reasonError("Agreed with the owner on a call")).toBeNull();
  });
});

describe("dashboard", () => {
  it("shows free trials apart from customers, with what needs a person", () => {
    expect(trialTileDetail({ waiting_for_review: 2, active: 9, ending_soon: 3, converted_this_month: 1 })).toBe(
      "3 ending within 7 days · 2 waiting for review · 1 converted this month",
    );
    expect(trialTileDetail(null)).toContain("apart from customers");
  });
});

describe("run 2: ending and deletion", () => {
  it("offers Run deletion now in Ending and deletion, no longer in Requests", () => {
    const ending = renderToStaticMarkup(
      <EndingAndDeletion onOpenTrial={() => undefined} onChanged={() => undefined} />,
    );
    expect(ending).toContain("Trials due for deletion");
    expect(ending).toContain("Run deletion now");
    const requests = renderToStaticMarkup(<TrialRequests />);
    expect(requests).not.toContain("Run deletion now");
    expect(requests).not.toContain("Delete expired trial data");
  });

  it("lists what the run deletes and what a hold keeps before it runs", () => {
    const html = renderToStaticMarkup(
      <RunDeletionNow
        initiallyOpen
        onDone={() => undefined}
        due={[
          { tenant_id: "a", tenant_key: "TRIAL_A", name: "OrbitCare", trial_ended_at: "2026-10-01T00:00:00Z" },
          {
            tenant_id: "b",
            tenant_key: "TRIAL_B",
            name: "PulseWatch",
            trial_ended_at: "2026-10-01T00:00:00Z",
            legal_hold: true,
          },
        ]}
      />,
    );
    expect(html).toContain("OrbitCare (TRIAL_A)");
    expect(html).toContain("PulseWatch (TRIAL_B), under a legal hold");
    expect(html).toContain("Delete data of 1 trial");
  });
});

describe("run 2: grace period and the AI slot", () => {
  it("shows a trial in its grace period as running, with the days to the grace end", () => {
    const html = render(
      trial({
        state: "ENDING_SOON",
        dates: {
          ...trial().dates,
          days_left: 5,
          in_grace: true,
          grace_ends_at: "2026-11-19T09:00:00+00:00",
          grace_ends_words: "19 Nov 2026, 14:30 IST",
        },
      }),
    );
    expect(html).toContain("5 days left (grace period)");
    expect(html).toContain("Grace period until");
    expect(html).toContain("19 Nov 2026, 14:30 IST · the users can still sign in");
    expect(html).not.toContain(">Ended<");
    expect(daysLeftText(1)).toBe("1 day left");
  });

  it("keeps a slot for the AI and usage panel, showing the server's line until the panel is passed", () => {
    const empty = render(trial());
    expect(empty).toContain('data-slot="trial-ai"');
    expect(empty).toContain("AI is off for free trials");
    const withPanel = renderToStaticMarkup(
      <TrialDetailView
        detail={trial()}
        history={[]}
        onAction={() => undefined}
        aiPanel={({ detail }) => <p>AI panel for {detail.name}</p>}
      />,
    );
    expect(withPanel).toContain("AI panel for OrbitCare Devices");
    expect(withPanel).not.toContain("AI is off for free trials");
  });

  it("opens with the trial name as the page title and the AI panel right under it, before the actions", () => {
    const html = renderToStaticMarkup(
      <TrialDetailView
        detail={trial()}
        history={[
          {
            id: "e1",
            action: "TRIAL_EXTENDED",
            actor_ref: null,
            created_at: "2026-11-10T09:00:00+00:00",
            details: { reason: "Owner asked for more time" },
          },
        ]}
        onAction={() => undefined}
        aiPanel={() => <p>AI panel here</p>}
      />,
    );
    expect(html).toMatch(/<h1 tabindex="-1">OrbitCare Devices<\/h1>/);
    expect(html.indexOf("AI panel here")).toBeLessThan(html.indexOf("Trial actions"));
    expect(html).toContain("AI use this month");
    // Sample counts in words, and the history says why.
    expect(html).toContain("<dt>Complaints</dt>");
    expect(html).toContain("Owner asked for more time");
  });
});

describe("the dashboard's Free trials tile (UX3)", () => {
  it("opens the requests while one waits for review, else the trials", async () => {
    const { trialTileItem } = await import("../console/AdminOverview");
    expect(trialTileItem({ waiting_for_review: 1 } as never)).toBe("Requests");
    expect(trialTileItem({ waiting_for_review: 0 } as never)).toBe("Trials");
    expect(trialTileItem(null)).toBe("Trials");
  });
});
