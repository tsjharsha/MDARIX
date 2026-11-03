/**
 * Separation of duties, shown honestly (0.10.71, A6): working alone in a trial, the owner approves their own practice
 * work (stage 3's practice exception, T-B8). Said at the button, wherever that approval is given.
 */
export const PRACTICE_APPROVAL = "Practice approval: in a pilot a colleague approves this.";

export function PracticeApproval({ shown }: { shown: boolean | undefined }) {
  return shown ? <small className="uw-practice-approval">{PRACTICE_APPROVAL}</small> : null;
}
