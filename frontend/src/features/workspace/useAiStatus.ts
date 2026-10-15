import { useEffect, useState } from "react";
import { requestJson } from "../../app/apiClient";
import { aiStatusBanner, type AiBanner, type AiStatus } from "./intelligence";

export const AI_STATUS_PATH = "/api/v1/ai/status";

/**
 * Whether AI can run for the organization right now (GET /api/v1/ai/status), as the banner to show when it cannot.
 * Null while loading, when AI can run, or when the status cannot be read: then nothing changes and the server still
 * decides each run.
 */
export function useAiBanner(): AiBanner | null {
  const [banner, setBanner] = useState<AiBanner | null>(null);
  useEffect(() => {
    let current = true;
    requestJson<AiStatus>(AI_STATUS_PATH)
      .then((status) => current && setBanner(aiStatusBanner(status)))
      .catch(() => current && setBanner(null));
    return () => {
      current = false;
    };
  }, []);
  return banner;
}

/**
 * Whether AI really answers for the organization now (GET /api/v1/ai/status): true or false once known, null while
 * loading. A status that cannot be read counts as false, so nothing starts in the AI's name on a guess.
 */
export function useAiReady(): boolean | null {
  const [ready, setReady] = useState<boolean | null>(null);
  useEffect(() => {
    let current = true;
    requestJson<AiStatus>(AI_STATUS_PATH)
      .then(
        (status) =>
          current && setReady(typeof status === "object" && status !== null && aiStatusBanner(status) === null),
      )
      .catch(() => current && setReady(false));
    return () => {
      current = false;
    };
  }, []);
  return ready;
}
