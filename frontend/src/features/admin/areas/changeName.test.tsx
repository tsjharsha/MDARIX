import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChangeNameDialog, NAME_MAX, canChangeName, cleanName, nameProblem, renameAccount } from "./ChangeName";

afterEach(() => vi.unstubAllGlobals());

describe("Platform Admin changes an account's name (Identity & Access › Platform users)", () => {
  it("trims the name and checks it as the server does: 1 to 120 characters, changed, no control characters", () => {
    expect(cleanName("  Asha   Rao ")).toBe("Asha Rao");
    expect(nameProblem("", "Asha")).toBe("Enter a name.");
    expect(nameProblem("    ", "Asha")).toBe("Enter a name.");
    expect(nameProblem("x".repeat(NAME_MAX + 1), "Asha")).toContain("at most 120 characters");
    expect(nameProblem("x".repeat(NAME_MAX), "Asha")).toBeNull();
    expect(nameProblem(" Asha ", "Asha")).toBe("This is the current name.");
    expect(nameProblem("Asha\u0000Rao", "Asha")).toBe("A name cannot contain control characters.");
    expect(nameProblem("Asha Rao", "Asha")).toBeNull();
    expect(nameProblem("Asha Rao", null)).toBeNull();
  });

  it("is offered for accounts of the administrator's own organization only (the route is scoped to it)", () => {
    expect(canChangeName({ tenant_id: "t-1" }, "t-1")).toBe(true);
    expect(canChangeName({ tenant_id: "t-2" }, "t-1")).toBe(false);
    expect(canChangeName({ tenant_id: "t-1" }, undefined)).toBe(false);
    expect(canChangeName({}, "t-1")).toBe(false);
  });

  it("sends only the trimmed name to the account's control-plane PATCH", async () => {
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", { setTimeout, clearTimeout, location: { pathname: "/platform-admin" } });
    await renameAccount("u-7", "  Asha   Rao ");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/admin/control-plane/users/u-7");
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ values: { display_name: "Asha Rao" } });
  });

  it("confirms the change in a dialog that names the account and says what stays the same", () => {
    const html = renderToStaticMarkup(
      <ChangeNameDialog
        account={{ id: "u-7", email: "asha@mdarix.invalid", display_name: "Asha" }}
        onClose={() => undefined}
        onDone={() => undefined}
      />,
    );
    expect(html).toContain("Confirm change · recorded in the audit trail");
    expect(html).toContain("Change the name of Asha?");
    expect(html).toContain("The email address (asha@mdarix.invalid), the role and the access stay as they are.");
    expect(html).toContain('value="Asha"');
    expect(html).toContain("1 to 120 characters.");
    // Nothing changed yet: the button waits for a new name.
    expect(html).toMatch(/<button type="submit" class="ac-primary" disabled="">Change name<\/button>/);
  });
});
