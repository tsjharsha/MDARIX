import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { FirstContact } from "./sections/FirstContact";
import { identifierChip, NEW_IDENTIFIER } from "./intake";

// 0.10.93 (B2 step 5, spec 4.2): Log a case with ID-1 ("Not sure", confirmed or unconfirmed with a source) and the
// S-1 issue category in plain words.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({ state: "ready", data: path ? resources.data[path.split("?")[0]] : null }),
  Drawer: ({ title, children }: { title: string; children: unknown }) => (
    <div data-title={title}>{children as never}</div>
  ),
}));

const GUIDE = {
  version: "case-check-starter-2",
  questions: [],
  answers: [],
  note: "",
  outcomes: [],
  table: [],
  requests: [{ code: "NONE", label: "Nothing" }],
  use_environments: [],
  user_types: [],
  harm_words: { version: "1", words: [] },
  fault_words: { version: "1", words: [] },
  levels: [],
  zones: ["UTC"],
  issue_categories: [
    { code: "MALFUNCTION", label: "Malfunction" },
    { code: "USAGE_HELP", label: "Usage help" },
  ],
  channels: [
    { code: "PHONE", label: "Phone" },
    { code: "REGULATOR", label: "Regulator notice" },
  ],
  patients: [
    { code: "NONE", label: "None" },
    { code: "NOT_KNOWN", label: "Not known" },
  ],
  identifiers: {
    keys: [
      { code: "product", label: "Product" },
      { code: "lot", label: "Lot" },
      { code: "serial", label: "Serial number" },
      { code: "udi", label: "UDI" },
    ],
    not_sure: ["version", "lot", "serial"],
    sources: [
      { code: "CALLER", label: "As told by the caller" },
      { code: "LABEL_OR_PHOTO", label: "Label or photo" },
    ],
  },
  starter_mark: "",
};

describe("Log a case (B2)", () => {
  it("offers Not sure for version, lot and serial only, and the issue category in plain words", () => {
    resources.data["/api/v1/intake"] = { summary: { all: 0, to_sign: 0, pending: 0, review: 0 }, items: [] };
    resources.data["/api/v1/intake/guide"] = GUIDE;
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider
        value={
          {
            session: { business_permissions: ["case.log"] },
            work: { products: [] },
            open: vi.fn(),
          } as unknown as WorkspaceApi
        }
      >
        <FirstContact part="calls" startLogging="CONTACT" />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain('data-title="Log a case"');
    expect(html.match(/Not sure<\/label>/g)).toHaveLength(3);
    expect(html).toContain("Usage help");
    expect(html).toContain("it never decides a complaint or a report");
    expect(html).toContain("Save the case");
    // Spec 4.2: the channel and its reference, patients and harm, what was tried, and who knew first.
    for (const text of [
      "Channel",
      "Regulator notice",
      "Reference in that channel (optional)",
      "Patients involved:",
      "What happened to the patient (optional)",
      "What was tried on the call",
    ])
      expect(html).toContain(text);
    expect(html.match(/name="patients"/g)).toHaveLength(2);
  });

  it("shows Not sure, Confirmed or Unconfirmed, and nothing for an empty identifier", () => {
    expect(identifierChip({ ...NEW_IDENTIFIER, not_sure: true }, false)?.label).toBe("Not sure");
    expect(identifierChip(NEW_IDENTIFIER, true)?.label).toBe("Unconfirmed");
    expect(identifierChip({ ...NEW_IDENTIFIER, status: "CONFIRMED", source: "LABEL_OR_PHOTO" }, true)?.label).toBe(
      "Confirmed",
    );
    expect(identifierChip(undefined, false)).toBeNull();
  });
});
