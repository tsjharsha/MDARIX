import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { DecisionTreesSection } from "./sections/DecisionTrees";
import { RuleRegister, RulesUsedPanel } from "./sections/RuleRegister";
import { WindowsBody } from "./sections/ReportingWindows";
import { inForceText, registerPath, rulesUsedLines, type RuleList, type RulesUsed } from "./ruleRegister";
import { legalOf, type Clock, type ReportabilitySettings } from "./reportability";
import { STARTER_LABEL } from "../shared/standards";

// B4 steps 9, 10 (screen) and 13: Decision trees › Rules (read-only, every member), the "Rules used" panel (at the
// event, today, decided), both hidden while the session says rule_register is off; FG-1's warning and legal deadline.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (ruleRegister: boolean, shownTab = "decision-trees?mode=rules") =>
  ({
    session: { allowed_menu: ["home"], business_permissions: ["records.read"], rule_register: ruleRegister },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    shownTab,
    reportTab: vi.fn(),
  }) as unknown as WorkspaceApi;

const render = (value: WorkspaceApi, node: React.ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const LIST: RuleList = {
  summary: { rules: 46, markets: 5, held_as_data: 6, starter_mark: "Starter, for your consultant to confirm." },
  kinds: [{ code: "REPORTABILITY_FLOOR", label: "Reportability floor" }],
  as_at: null,
  items: [
    {
      code: "US-floor-1",
      rule: "US-floor",
      version: 1,
      version_words: "version 1",
      kind: "REPORTABILITY_FLOOR",
      kind_label: "Reportability floor",
      market: "US",
      market_label: "United States (FDA)",
      title: "US medical device reporting",
      plain: "Death or serious injury: report in 30 days.",
      source: [{ id: "CFR803_50", short: "21 CFR 803.50", title: "Reports", clause: "21 CFR 803.50(a)" }],
      effective_from: null,
      effective_to: null,
      state: "IN_FORCE",
      law_in_force_from: null,
      change: { kind: "INITIAL", reason: "Today's logic" },
      approved_by: "Owner",
      approved_on: "2026-11-11",
      held_as: "DATA",
      pinned: false,
      fingerprint: "a1b2c3d4e5f6",
      starter_mark: "Starter, for your consultant to confirm.",
    },
  ],
};

const USED: RulesUsed = {
  at_event: {
    code: "US-floor-1",
    title: "US medical device reporting",
    day: "2026-11-02",
    rules_applied: { rules: [{ id: "F-US-1", state: "APPLIES" }], type_row: "T-US-1" },
  },
  today: { code: "US-floor-2", same: false },
  decided: null,
};

describe("Decision trees › Rules", () => {
  it("lists every rule flat, with its version, source, dates and fingerprint", () => {
    resources.data["/api/v1/rule-register"] = LIST;
    const html = render(api(true), <RuleRegister />);
    expect(html).toContain("46 rules · 5 markets · 6 held as data");
    expect(html.split(STARTER_LABEL).length - 1).toBe(1);
    expect(html).not.toContain("consultant");
    expect(html).toContain("US medical device reporting");
    expect(html).toContain("<code>US-floor-1</code>");
    expect(html).toContain("21 CFR 803.50(a)");
    expect(html).toContain("From the start");
    expect(html).toContain("a1b2c3d4e5f6");
    expect(html).toContain("As at");
    expect(html).not.toMatch(/gradient|glass|glow/); // G-2: flat below the header
  });

  it("is a mode of Decision trees only while the register is on", () => {
    resources.data["/api/v1/decision-trees"] = { markets: [], complaints: [] };
    resources.data["/api/v1/rule-register"] = LIST;
    const on = render(api(true), <DecisionTreesSection />);
    expect(on).toContain(">Rules</button>");
    expect(on).toContain("46 rules");
    const off = render(api(false), <DecisionTreesSection />);
    expect(off).not.toContain(">Rules</button>");
    expect(off).not.toContain("46 rules");
  });

  it("builds the register's address with only the filters chosen", () => {
    expect(registerPath({})).toBe("/api/v1/rule-register");
    expect(registerPath({ market: "US", asAt: "2027-03-01" })).toBe("/api/v1/rule-register?market=US&as_at=2027-03-01");
    expect(inForceText({ effective_from: null, effective_to: null })).toBe("From the start");
    expect(inForceText({ effective_from: "2027-03-01", effective_to: null })).toMatch(/^From .*2027$/);
  });
});

describe("Rules used", () => {
  it("keeps the event, today and the decision apart", () => {
    const lines = rulesUsedLines(USED)!;
    expect(lines.atEvent).toContain("US starter rules (version 1), in force on");
    expect(lines.atEvent).toContain("the awareness day");
    expect(lines.atEvent).toContain("F-US-1 applies");
    expect(lines.today).toContain("US starter rules (version 2): differs; not applied to this event");
    expect(lines.decided).toBe("Not signed yet.");
    const html = renderToStaticMarkup(<RulesUsedPanel used={USED} />);
    expect(html).toContain("At the event");
    expect(html).toContain("Today");
    expect(html).toContain("Decided");
  });

  it("says a conclusion signed before the register keeps what it signed, and one after names its floor", () => {
    const before = { ...USED, today: { code: "US-floor-1", same: true } };
    const old = { floor_code: null, before_register: true, rules_applied: null, date_calc: null, fingerprint: "f" };
    expect(rulesUsedLines({ ...before, decided: old })!.decided).toBe(
      "Signed before the rule register: it keeps what it signed.",
    );
    const signed = {
      ...old,
      floor_code: "US-floor-1",
      before_register: false,
      rules_applied: USED.at_event.rules_applied,
    };
    expect(rulesUsedLines({ ...before, decided: signed })!.decided).toContain(
      "Signed under US starter rules (version 1). F-US-1 applies",
    );
    expect(rulesUsedLines(before)!.today).toBe("US starter rules (version 1): the same.");
  });

  it("leaves out rules that were not recorded rather than saying none applied (F-M2)", () => {
    const lines = rulesUsedLines({ ...USED, at_event: { ...USED.at_event, rules_applied: null } })!;
    expect(lines.atEvent).not.toContain("not recorded");
    expect(lines.atEvent).toMatch(/the awareness day\.$/);
    expect(lines.atEvent).not.toContain("No floor rule applies");
  });

  it("is hidden while the register is off (no rules_used)", () => {
    expect(renderToStaticMarkup(<RulesUsedPanel used={null} />)).toBe("");
    expect(rulesUsedLines(undefined)).toBeNull();
  });
});

describe("FG-1: a window longer than the law", () => {
  it("warns on the windows screen and never hides the window", () => {
    const window = {
      name: "US 60 days",
      markets: ["US"],
      triggers: ["DEATH"],
      days: 60,
      day_basis: "CALENDAR",
      note: null,
      basis: [],
    };
    const settings = {
      windows: [window],
      lookback_days: 365,
      configured: true,
      templates: [],
      version: 2,
      updated_by_name: null,
      updated_at: null,
      longer_than_law: [
        {
          window: "US 60 days",
          market: "US",
          market_label: "United States (FDA)",
          legal: "30-calendar-day report (21 CFR 803.50)",
          message:
            "“US 60 days” can end after the longest legal period for United States (FDA) (30-calendar-day report).",
        },
      ],
    } as unknown as ReportabilitySettings;
    const html = render(api(true), <WindowsBody settings={settings} onSaved={() => undefined} />);
    expect(html).toContain("can end after the longest legal period for United States (FDA)");
    expect(html).toContain("tone-warning");
  });

  it("takes the earliest legal deadline of the clocks that carry one", () => {
    const clock = (due: string, legal?: string) =>
      ({
        window: "w",
        due_date: due,
        legal: legal ? { label: "law", due_date: legal } : undefined,
      }) as unknown as Clock;
    expect(legalOf({ clocks: [clock("2027-03-05")] })).toBeNull();
    expect(legalOf({ clocks: [clock("2027-03-05", "2027-02-10"), clock("2027-03-01", "2027-02-03")] })?.due_date).toBe(
      "2027-02-03",
    );
  });
});
