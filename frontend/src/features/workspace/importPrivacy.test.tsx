import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ImportPanel } from "./sections/ImportData";
import { TRIAL_SET_ASIDE_NOTE } from "./sections/ImportReports";

// 0.10.62: set-aside rows are stored with every free-text value masked (J7), so the trial can say so plainly.
function render(isTrial: boolean) {
  const api = { session: { business_permissions: ["records.write"] }, isTrial, work: {} } as unknown as WorkspaceApi;
  return renderToStaticMarkup(
    <WorkspaceContext.Provider value={api}>
      <ImportPanel
        templates={[{ entity: "complaints", title: "Complaints", required: [], optional: [] } as never]}
        basePath="/api/v1/trial/imports"
        onImported={vi.fn()}
      />
    </WorkspaceContext.Provider>,
  );
}

describe("the import panel's privacy line", () => {
  it("says in a trial that set-aside rows are kept masked and deleted with the trial", () => {
    expect(TRIAL_SET_ASIDE_NOTE).toBe(
      "In a free trial, rows set aside on import are kept with personal details masked so you can review and fix them, and are deleted with the trial.",
    );
    expect(render(true)).toContain(TRIAL_SET_ASIDE_NOTE);
    expect(render(false)).not.toContain(TRIAL_SET_ASIDE_NOTE);
  });
});
