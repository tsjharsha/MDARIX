import { describe, expect, it } from "vitest";
import { ApiError } from "./apiClient";
import { afterSessionRefusal } from "./PrivateApp";

describe("the session check's refusals", () => {
  it("shows an ended trial its trial-ended page instead of sending it to sign-in (J25)", () => {
    expect(afterSessionRefusal(new ApiError("Your MDARIX free trial has ended.", 403, "TRIAL_ENDED"))).toBe(
      "TRIAL_ENDED",
    );
  });

  it("keeps trying through an outage and sends an ended session to sign-in", () => {
    expect(afterSessionRefusal(new ApiError("down", 503))).toBe("RETRY");
    expect(afterSessionRefusal(new ApiError("idle", 401, "SESSION_IDLE_TIMEOUT"))).toBe("IDLE");
    expect(afterSessionRefusal(new ApiError("gone", 401, "UNAUTHENTICATED"))).toBe("SIGN_IN");
    expect(afterSessionRefusal(new ApiError("x", 403, "TENANT_ACCESS_SUSPENDED"))).toBe("SIGN_IN");
  });
});
