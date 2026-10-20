import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { Profile } from "./sections/Account";

// Release 0.10.36 (UX-27): a free trial has no administrator, and its people never need the internal IDs.
function render(isTrial: boolean) {
  const api = {
    session: {
      display_name: "Asha Rao",
      email: "asha.rao@orbit.example",
      business_id: "USR000008",
      tenant_business_id: "TEN000004",
      current_tenant: { tenant_name: "Orbit Medical Devices" },
      environment: "PRODUCTION",
      role: "LEADER",
    },
    isTrial,
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn() },
  } as unknown as WorkspaceApi;
  return renderToStaticMarkup(
    <WorkspaceContext.Provider value={api}>
      <Profile />
    </WorkspaceContext.Provider>,
  );
}

describe("My account", () => {
  it("in a free trial shows no internal IDs and says whom to write to, not an administrator", () => {
    const html = render(true);
    expect(html).toContain("Asha Rao");
    expect(html).toContain("Orbit Medical Devices");
    expect(html).not.toContain("USR000008");
    expect(html).not.toContain("TEN000004");
    expect(html).not.toContain("User ID");
    expect(html).not.toContain("administrator");
    expect(html).toContain("This is a free trial workspace. To change your name or email, write to");
    expect(html).toContain('href="mailto:support@mdarix.in"');
  });

  it("elsewhere keeps the IDs and the administrator line", () => {
    const html = render(false);
    expect(html).toContain("USR000008");
    expect(html).toContain("Orbit Medical Devices · TEN000004");
    expect(html).toContain("managed by your organization&#x27;s administrator");
    expect(html).not.toContain("free trial workspace");
  });
});
