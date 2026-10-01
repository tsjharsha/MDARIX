import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { useCan, WorkspaceContext, type WorkspaceApi } from "./workspaceContext";

function Probe() {
  return <span>{[useCan("ai.run"), useCan("records.write"), useCan("regulatory.approve")].join(",")}</span>;
}

const withSession = (session: WorkspaceApi["session"]) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={{ session } as WorkspaceApi}>
      <Probe />
    </WorkspaceContext.Provider>,
  );

describe("useCan", () => {
  it("follows the business permissions the server sent", () => {
    expect(withSession({ business_permissions: ["ai.run", "records.write"] })).toContain("true,true,false");
    expect(withSession({ business_permissions: [] })).toContain("false,false,false");
  });

  it("leaves controls visible when permissions are unknown (the server still decides)", () => {
    expect(withSession({})).toContain("true,true,true");
    expect(renderToStaticMarkup(<Probe />)).toContain("true,true,true");
  });
});
