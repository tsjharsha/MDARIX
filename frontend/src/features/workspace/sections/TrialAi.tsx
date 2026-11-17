import { useState } from "react";
import { ConsoleContext, type ConsoleApi } from "../../customer-admin/context";
import { ConfirmDialog, useResource, type Confirmation } from "../../customer-admin/shared";
import { AI_SETTINGS_PATH, AiProcessing, type AiSettings } from "../../customer-admin/sections/Security";
import { useIsTrial, useWorkspace } from "../workspaceContext";

/** The Settings tab where the person who started a free trial switches AI on for the sample data (F1, decision T5). */
export const TRIAL_AI_TAB = "AI on the sample data";

/**
 * Whether the signed-in person may switch the trial's AI: the server answers the AI settings only to the person who
 * started the trial (403 to everyone else). ``can_change`` only says whether the switch can move now.
 */
export function useTrialAiOwner(): boolean {
  const trial = useIsTrial();
  const settings = useResource<AiSettings>(trial ? AI_SETTINGS_PATH : null);
  return Boolean(trial && settings.data?.free_trial);
}

/** The customer-admin AI switch, in the workspace: its confirmation dialog and messages use the workspace's own. */
export function TrialAiSettings() {
  const { notify } = useWorkspace();
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const api: ConsoleApi = { context: null, open: () => undefined, confirm: setConfirmation, notify };
  return (
    <ConsoleContext.Provider value={api}>
      <AiProcessing trialOwner />
      <ConfirmDialog
        request={confirmation}
        onClose={() => setConfirmation(null)}
        onDone={(text) => {
          setConfirmation(null);
          notify(text);
        }}
      />
    </ConsoleContext.Provider>
  );
}
