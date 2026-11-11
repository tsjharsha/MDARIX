import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PERSONAL_OPTION, exportRequest } from "./sections/Organization";
import { ConfirmDialog } from "./shared";

// B8 follow-up (owner, 11 Nov, "tick-box"): the export leaves out patient and reporter details unless ticked.
describe("Export: include patient and reporter details", () => {
  it("asks for them only when ticked, and then with contacts unmasked", () => {
    expect(exportRequest("Copy for our records", "", false)).toEqual({ reason: "Copy for our records" });
    expect(exportRequest("Notified body asked", "123456", true)).toEqual({
      reason: "Notified body asked",
      mfa_code: "123456",
      unmask_contacts: true,
      include_personal: true,
    });
  });

  it("shows the option unticked, with a plain warning, and does not block the export", () => {
    const html = renderToStaticMarkup(
      <ConfirmDialog
        request={{
          title: "Prepare a full export?",
          body: "Body",
          confirmLabel: "Prepare export",
          option: PERSONAL_OPTION,
          run: async () => undefined,
          done: "Done",
        }}
        onClose={() => undefined}
        onDone={() => undefined}
      />,
    );
    expect(html).toContain("Include patient and reporter details from submitted reports");
    expect(html).toContain("Off by default");
    expect(html).toMatch(/<input type="checkbox"\/>/);
    expect(html).not.toMatch(/<button[^>]*disabled[^>]*>Prepare export/);
  });
});
