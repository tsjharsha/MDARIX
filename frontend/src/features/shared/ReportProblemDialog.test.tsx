import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { trialTabFor } from "../workspace/sections/GettingStarted";

// The dialog is portalled to the end of the page; rendered in place here so its markup can be read.
vi.mock("react-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-dom")>()),
  createPortal: (children: ReactNode) => children,
}));

const { ReportProblemDialog } = await import("./ReportProblem");

describe("Report a problem", () => {
  it("carries the workspace's colours and type to the end of the page, where it is rendered", () => {
    vi.stubGlobal("document", { body: {} }); // the portal's target; the test runs without a page
    const markup = renderToStaticMarkup(<ReportProblemDialog onClose={() => undefined} />);
    vi.unstubAllGlobals();
    expect(markup.startsWith('<div class="admin-console ac-portal"><div class="ac-modal-backdrop"')).toBe(true);
    expect(markup).toContain("Report a problem");
  });
});

describe("Help, Getting started and import templates", () => {
  it("names the Your data tab, where the import templates are", () => {
    expect(trialTabFor("Your data")).toBe("Your data");
    expect(trialTabFor("Readiness")).toBeUndefined();
    expect(trialTabFor(undefined)).toBeUndefined();
  });
});
