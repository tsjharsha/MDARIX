import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { roleNote, shortRoles } from "../../app/roles";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { FLAGSHIP, SCENARIOS, onStoryRecord, storyStep } from "./entrance";
import { StoryBar } from "./sections/Entrance";
import { ProblemCode, problemCodeText } from "./sections/ProblemCode";
import { attentionText } from "./sections/ComplaintPage";
import { caseVersion, chosenInvestigation } from "./useWorkContext";
import { CaseProgressLine } from "./sections/CaseHeader";
import { Panel } from "../admin/console/charts";

// 0.10.70, "Polish before proof": the stage 8 leftovers.

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "loading", data: null, reload: () => undefined }),
}));

const flagship = SCENARIOS.find((item) => item.key === "reportable")!;
const rising = SCENARIOS.find((item) => item.key === "rising")!;
const api = (story: string | null, investigationId = "") =>
  ({
    session: null,
    work: { investigationId },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    story,
    startStory: vi.fn(),
  }) as unknown as WorkspaceApi;

describe("item 7: the story bar counts steps only on the story's own record", () => {
  it("is off the story's path on another complaint, with the way back to the story", () => {
    const place = { section: "Complaint", tab: "Summary?ref=SAMPLE-RV-06" };
    expect(storyStep(flagship, place)).toBe(0); // by place alone it read "Step 1 of 7" on RV-06
    expect(onStoryRecord(flagship, place, {})).toBe(false);
    expect(onStoryRecord(flagship, { section: "Complaint", tab: `Summary?ref=${FLAGSHIP}` }, {})).toBe(true);
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api("reportable")}>
        <StoryBar section="Complaint" tab="Summary?ref=SAMPLE-RV-06" />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain("Off the story&#x27;s path");
    expect(html).toContain("Back to the story");
    expect(html).not.toContain("Step 1 of 7");
  });

  it("knows a complaint by its id in a list's panel, and an investigation by the one in the context", () => {
    const ids = { complaintId: "c-flagship", caseId: "inv-flagship" };
    expect(onStoryRecord(flagship, { section: "Complaints", tab: "Reporting?complaint=c-other" }, ids)).toBe(false);
    expect(onStoryRecord(flagship, { section: "Complaints", tab: "Reporting?complaint=c-flagship" }, ids)).toBe(true);
    expect(onStoryRecord(flagship, { section: "Investigations", tab: "Summary" }, ids, "inv-orbit")).toBe(false);
    expect(onStoryRecord(flagship, { section: "Investigations", tab: "Summary" }, ids, "inv-flagship")).toBe(true);
    // Before the flagship's disposition no investigation is the story's: SAMPLE-INV-001 read "Step 6 of 7".
    expect(onStoryRecord(flagship, { section: "Investigations" }, { caseId: null }, "inv-orbit")).toBe(false);
    // "Is a problem rising?" is SAMPLE-INV-001's story.
    expect(onStoryRecord(rising, { section: "Investigations" }, { caseId: "inv-orbit" }, "inv-orbit")).toBe(true);
    expect(onStoryRecord(rising, { section: "Investigations" }, { caseId: "inv-orbit" }, "inv-flagship")).toBe(false);
  });

  it("keeps the last step once ready to close is signed and its receipt is in History", () => {
    expect(storyStep(flagship, { section: "Complaint", tab: `History?ref=${FLAGSHIP}` })).toBe(6);
  });
});

describe("item 2: a problem code reads by its IMDRF term, the customer's code as its detail", () => {
  const links = {
    UNDER_INFUSION_NO_ALARM: [
      { release: "2025", annex: "A", code: "A14", term: "Infusion or Flow Problem" },
      { release: "2025", annex: "A", code: "A16", term: "Protective Measures Problem" },
    ],
  };
  it("puts the term first and keeps the code, never altered", () => {
    const html = renderToStaticMarkup(<ProblemCode code="UNDER_INFUSION_NO_ALARM" links={links} />);
    expect(html.indexOf("Infusion or Flow Problem; Protective Measures Problem")).toBeLessThan(
      html.indexOf("UNDER_INFUSION_NO_ALARM"),
    );
    expect(html).toContain("your code <code>UNDER_INFUSION_NO_ALARM</code>");
    expect(problemCodeText("UNDER_INFUSION_NO_ALARM", links)).toBe(
      "Infusion or Flow Problem; Protective Measures Problem (IMDRF A14, A16) · your code UNDER_INFUSION_NO_ALARM",
    );
  });
  it("shows an unmapped code as the customer's own, and says so once the links are read", () => {
    const html = renderToStaticMarkup(<ProblemCode code="SPO2_READING_HIGH" links={{}} loaded />);
    expect(html).toContain("<code>SPO2_READING_HIGH</code>");
    expect(html).toContain("your code; no IMDRF term mapped yet");
  });
});

describe("item 6: the top bar's name and role on one line", () => {
  const session = { roles: [{ code: "LEADER", label: "Leader (Quality Manager)" }] };
  it("shortens the role; the whole one is the tooltip", () => {
    expect(shortRoles(session)).toBe("Leader");
    expect(shortRoles({ roles: [] })).toBe("No active role");
  });
  it("never nests brackets after a name", () => {
    expect(roleNote("LEADER", "Leader (Quality Manager)")).toBe(" (Leader, Quality Manager)");
    expect(roleNote("APPROVER", "Approver")).toBe(" (Approver)");
  });
});

describe("items 4 and 8: what needs attention reads as what is open", () => {
  it("names what is missing, not the check's goal, and a finished event asks for nothing", () => {
    const blocked = [{ label: "Triage is complete", detail: "On the triage list: its triage record is not complete" }];
    expect(attentionText(blocked, true)).toBe("1 open: On the triage list: its triage record is not complete");
    expect(attentionText(blocked, false)).toBe("Nothing: 1 item was signed open, with a reason");
    expect(attentionText([], false)).toBe("Nothing open");
  });
});

describe("items 9 and 10: the investigation's context comes from the record being opened", () => {
  const orbit = { id: "inv-orbit", status: "open", version_identifier: "Rev B" };
  const pulseOld = { id: "inv-pulse-old", status: "open", version_identifier: "Rev B" };
  const flagshipCase = { id: "inv-flagship", status: "open", version_identifier: "Rev A" };
  it("opens the investigation asked for, never the previous one or the first in the list", () => {
    expect(chosenInvestigation([pulseOld, flagshipCase], "inv-flagship", "inv-orbit", false)).toBe("inv-flagship");
    // Just opened, not in a list read a moment before: read the list again, never the first in the list.
    expect(chosenInvestigation([pulseOld], "inv-flagship", "inv-orbit", false)).toBeNull();
    expect(chosenInvestigation([pulseOld], "inv-flagship", "inv-orbit", true)).toBe("inv-pulse-old");
    // Nothing asked for: the one shown stays when listed, else the product's first open one.
    expect(chosenInvestigation([pulseOld, flagshipCase], "", "inv-flagship", false)).toBe("inv-flagship");
    expect(chosenInvestigation([pulseOld, flagshipCase], "", "inv-orbit", false)).toBe("inv-pulse-old");
  });
  it("shows it on its own version, not the version the previous record was on", () => {
    expect(caseVersion(flagshipCase, ["Rev A", "Rev B"])).toBe("Rev A");
    expect(caseVersion(orbit, ["Rev A", "Rev B"])).toBe("Rev B");
    // A version the product does not have, or none recorded: the context keeps the product's own choice.
    expect(caseVersion({ ...flagshipCase, version_identifier: "Rev Z" }, ["Rev A", "Rev B"])).toBeNull();
    expect(caseVersion({ id: "x" }, ["Rev A"])).toBeNull();
  });
});

describe("item 10: an investigation opened a moment ago never claims more than it has read", () => {
  it("says it is reading its steps, not that every step is done", () => {
    const html = renderToStaticMarkup(<CaseProgressLine steps={[]} onSection={vi.fn()} />);
    expect(html).toContain("Reading where this investigation stands…");
    expect(html).not.toContain("Every step is done");
  });
  it("a loading panel says it is reading: never an empty grey box", () => {
    const html = renderToStaticMarkup(
      <Panel title="Human decision" state="loading">
        {null}
      </Panel>,
    );
    expect(html).toContain("Reading…");
  });
});
