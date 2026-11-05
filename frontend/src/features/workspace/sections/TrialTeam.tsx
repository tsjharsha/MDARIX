import { useState } from "react";
import { Lock, Pencil } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { Panel } from "../../admin/console/charts";
import { ConfirmDialog, send, useResource, type Confirmation, type Resource } from "../../customer-admin/shared";
import { TrialSupportAccess } from "./TrialSupportAccess";

export const TEAM_PATH = "/api/v1/trial/team";

export type TeamMember = {
  id: string;
  display_name: string;
  email: string;
  status: string;
  is_owner: boolean;
  is_you: boolean;
  /** An invitation whose link no longer works: shown as Expired, with Resend invitation. */
  invitation_expired?: boolean;
  /** The person's persona (0.10.73): a colleague's is their real role, set by the owner (locked to them). */
  persona?: string;
  persona_label?: string;
  persona_locked?: boolean;
  /** Every persona the owner gave the colleague (0.10.82, D1.9): their roles add up. */
  personas?: Array<{ code: string; label: string }>;
};

/** A persona the owner may give a colleague (access_control/personas.py COLLEAGUE_PERSONAS). */
export type TeamPersona = { code: string; label: string; sub: string };
export type Team = {
  can_invite: boolean;
  /** Remove colleagues, reset their MFA, decide on support access: the trial owner only. */
  can_manage?: boolean;
  limit: number;
  seats_used: number;
  members: TeamMember[];
  personas?: TeamPersona[];
};

export type MemberAction = "resend" | "mfa-reset" | "remove";

/** What the trial owner can do for one person of the team (nothing for themself, nothing for a colleague viewer). */
export function memberActions(member: TeamMember, team: Pick<Team, "can_invite" | "can_manage">): MemberAction[] {
  const actions: MemberAction[] = [];
  if (team.can_invite && member.status === "INVITED") actions.push("resend");
  if (!team.can_manage || member.is_you || member.is_owner) return actions;
  if (member.status === "ACTIVE") actions.push("mfa-reset");
  return [...actions, "remove"];
}

/** How a person's place on the team reads: Active, Invited, or Expired (an invitation link that no longer works). */
export const memberStatus = (member: TeamMember) =>
  member.status === "ACTIVE" ? "Active" : member.invitation_expired ? "Invitation expired" : "Invited";

/** The confirmation for taking a colleague off the trial, or withdrawing an invitation not yet accepted. */
export function removeConfirmation(member: TeamMember, onDone: () => void): Confirmation {
  const name = member.display_name || member.email;
  const invited = member.status === "INVITED";
  return {
    title: invited ? `Withdraw the invitation to ${name}?` : `Remove ${name} from your trial?`,
    body: invited
      ? "The invitation link stops working at once, and the seat is free for someone else."
      : "This ends their access to your trial now: they are signed out at once and can no longer sign in. Everything they did stays in MDARIX under their name, and their seat is free for someone else. You can invite them again later.",
    confirmLabel: "Remove from trial",
    danger: true,
    done: invited ? `The invitation to ${name} is withdrawn.` : `${name} is removed from your trial.`,
    run: async () => {
      await send(`${TEAM_PATH}/${member.id}/remove`, "POST");
      onDone();
    },
  };
}

/** The confirmation for resetting a colleague's MFA after they lost their authenticator and recovery codes. */
export function mfaResetConfirmation(member: TeamMember, onDone: () => void): Confirmation {
  const name = member.display_name || member.email;
  return {
    title: `Reset multi-factor authentication for ${name}?`,
    body: "Use this when they lost their authenticator app and recovery codes. Their authenticator is removed, they are signed out, and they set up a new one at their next sign-in.",
    confirmLabel: "Reset MFA",
    reason: { label: "Why is the authenticator being reset?", min: 5 },
    done: `${name} sets up a new authenticator at their next sign-in.`,
    run: async (reason) => {
      await send(`${TEAM_PATH}/${member.id}/mfa-reset`, "POST", { reason });
      onDone();
    },
  };
}

/** "Regulatory Leader + Decision Maker". */
export const personaList = (personas: ReadonlyArray<{ label: string }>) =>
  personas.map((item) => item.label).join(" + ");

/** The confirmation for giving a colleague other personas, and with them their roles (0.10.73; several, 0.10.82). */
export function personaConfirmation(
  member: TeamMember,
  personas: readonly TeamPersona[],
  onDone: () => void,
): Confirmation {
  const name = member.display_name || member.email;
  const names = personaList(personas);
  return {
    title: `Make ${name} a ${names}?`,
    body: `${name} then sees ${personas.length > 1 ? "each persona's" : `the ${names}'s`} screens, switches between them, and signs as ${personas.length > 1 ? "their roles together" : "its role"}: ${personas.map((item) => item.sub).join("; ")}. Nobody approves what they prepared themselves. Their earlier work stays as it was. Only you can change it again.`,
    confirmLabel: personas.length > 1 ? "Change the personas" : "Change the persona",
    done: `${name} is now a ${names}.`,
    run: async () => {
      await send(`${TEAM_PATH}/${member.id}/persona`, "POST", { personas: personas.map((item) => item.code) });
      onDone();
    },
  };
}

/** One or more personas, ticked (0.10.82, D1.9). */
function PersonaTicks({
  personas,
  chosen,
  onChange,
  legend,
  disabled = false,
}: {
  personas: readonly TeamPersona[];
  chosen: readonly string[];
  onChange: (codes: string[]) => void;
  legend: string;
  disabled?: boolean;
}) {
  return (
    <fieldset className="uw-team-ticks">
      <legend>{legend}</legend>
      {personas.map((item) => (
        <label key={item.code} className="ca-check">
          <input
            type="checkbox"
            checked={chosen.includes(item.code)}
            disabled={disabled}
            onChange={(event) =>
              onChange(event.target.checked ? [...chosen, item.code] : chosen.filter((code) => code !== item.code))
            }
          />{" "}
          <span>
            <b>{item.label}</b> <small className="ac-muted">{item.sub}</small>
          </span>
        </label>
      ))}
    </fieldset>
  );
}

/** A colleague's personas, changed by the owner: tick, then confirm. */
function ChangePersonas({
  member,
  personas,
  busy,
  onConfirm,
  onChanged,
}: {
  member: TeamMember;
  personas: readonly TeamPersona[];
  busy: boolean;
  onConfirm: (request: Confirmation) => void;
  onChanged: () => void;
}) {
  const held = (member.personas ?? []).map((item) => item.code);
  const [chosen, setChosen] = useState<string[]>(held.length ? held : member.persona ? [member.persona] : []);
  const picked = personas.filter((item) => chosen.includes(item.code));
  const same = picked.map((item) => item.code).join() === held.join();
  return (
    <details className="uw-team-change">
      {/* A control the owner changes: its own word, never the lock that means "set for you" (0.10.84, L2). */}
      <summary>
        {personaList(member.personas?.length ? member.personas : picked)} ·{" "}
        <span className="ac-link">
          <Pencil size={13} aria-hidden="true" /> Change
        </span>
        <span className="ca-sr-only"> the personas of {member.display_name || member.email}</span>
      </summary>
      <PersonaTicks personas={personas} chosen={chosen} onChange={setChosen} legend="Personas" disabled={busy} />
      <button
        type="button"
        className="ac-secondary"
        disabled={busy || !picked.length || same}
        onClick={() => onConfirm(personaConfirmation(member, picked, onChanged))}
      >
        Save the personas
      </button>
    </details>
  );
}

type Message = { tone: "good" | "bad"; text: string; link?: string };

/**
 * Getting started › Team: who is on the trial, and, for the person who started it, inviting colleagues up to the
 * trial's limit, removing one (the seat is free again), resetting a colleague's MFA, and deciding on the support access
 * MDARIX asks for (backend/app/trial/team.py). A trial has no admin console: these are its owner's.
 */
/** The invitation is sent while the request waits: a slow e-mail provider can take up to its own 15-second limit on
 * top of the save, so the screen waits longer than the usual 15 seconds before it gives up (0.10.88, DEV-10). */
export const INVITE_TIMEOUT_MS = 45_000;

/** What to say when an invitation got no answer (a timeout or a lost connection): it may have been made and sent, so
 * "try again" would invite twice. Null for any other failure, whose own message is shown. Exported for its test. */
export function unansweredInvite(error: unknown): string | null {
  const code = (error as { code?: string } | null)?.code;
  if (code !== "TIMEOUT" && code !== "NETWORK_ERROR") return null;
  return "MDARIX did not answer in time. The invitation may still have been sent: check the list below before you send it again.";
}

export function TeamPanel({ onChanged }: { onChanged: () => void }) {
  const team = useResource<Team>(TEAM_PATH);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const changed = () => {
    team.reload();
    onChanged();
  };

  const invite = async (path: string, body?: object) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await requestJson<any>(path, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
        timeoutMs: INVITE_TIMEOUT_MS,
      });
      const sent = result.email_delivery === "SENT";
      const link = !sent && result.activation_path ? `${window.location.origin}${result.activation_path}` : undefined;
      setMessage(
        sent
          ? { tone: "good", text: `Invitation emailed to ${result.email}. The link is valid for 48 hours.` }
          : link
            ? {
                tone: "good",
                text: `Email is not set up on this development server. Send ${result.email} this one-time link (valid 48 hours):`,
                link,
              }
            : {
                tone: "bad",
                text: `The invitation email to ${result.email} could not be sent. Try Resend in a few minutes, or contact MDARIX support.`,
              },
      );
      changed();
      return true;
    } catch (error) {
      const unanswered = unansweredInvite(error);
      setMessage({
        tone: "bad",
        text: unanswered ?? (error instanceof Error ? error.message : "The invitation could not be sent."),
      });
      // The invitation may well be there: the list shows what the server did.
      if (unanswered) changed();
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <TeamView
        team={team}
        busy={busy}
        message={message}
        onInvite={(email, name, personas) => invite(TEAM_PATH, { email, display_name: name, personas })}
        onResend={(member) => void invite(`${TEAM_PATH}/${member.id}/resend-invitation`)}
        onConfirm={(request) => {
          setMessage(null);
          setConfirm(request);
        }}
        onChanged={changed}
      />
      {team.data?.can_manage && <TrialSupportAccess />}
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          setMessage({ tone: "good", text });
        }}
      />
    </>
  );
}

/** The team as the server sent it (separate from the requests, so it renders on its own in tests). */
export function TeamView({
  team,
  busy,
  message,
  onInvite,
  onResend,
  onConfirm,
  onChanged,
}: {
  team: Resource<Team>;
  busy: boolean;
  message: Message | null;
  onInvite: (email: string, name: string, personas: string[]) => Promise<boolean>;
  onResend: (member: TeamMember) => void;
  onConfirm: (request: Confirmation) => void;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [ticked, setTicked] = useState<string[]>(["quality"]);
  const data = team.data;
  const full = !!data && data.seats_used >= data.limit;
  const personas = data?.personas ?? [];
  return (
    <Panel
      title="Your trial team"
      eyebrow={
        data ? `${data.seats_used} ${data.seats_used === 1 ? "person" : "people"} · up to ${data.limit}` : "Team"
      }
      source={team}
    >
      {data && (
        <>
          {data.can_invite && (
            <p className="ac-muted">
              Invite as many colleagues as you need. Tick one or more personas for each: they are their roles. They see
              each persona's screens and switch between them; their rights add up, but nobody approves what they
              prepared. Only you can change them.
            </p>
          )}
          <ul className="uw-team">
            {data.members.map((member) => (
              <li key={member.id}>
                <div>
                  <strong>
                    {member.display_name}
                    {member.is_you && <span className="uw-team-tag">You</span>}
                    {member.is_owner && <span className="uw-team-tag">Trial owner</span>}
                  </strong>
                  <small>{member.email}</small>
                </div>
                {member.persona_label && !(data.can_manage && !member.is_owner && personas.length > 0) && (
                  <span
                    className="ms-chip uw-team-persona"
                    title={member.persona_locked ? "Set by the trial owner" : undefined}
                  >
                    {member.personas?.length ? personaList(member.personas) : member.persona_label}
                    {member.persona_locked && <Lock size={12} aria-label="set by the trial owner" />}
                  </span>
                )}
                <span className={`uw-team-status ${member.status === "ACTIVE" ? "is-active" : ""}`}>
                  {memberStatus(member)}
                </span>
                {data.can_manage && !member.is_owner && personas.length > 0 && (
                  <ChangePersonas
                    member={member}
                    personas={personas}
                    busy={busy}
                    onConfirm={onConfirm}
                    onChanged={onChanged}
                  />
                )}
                {memberActions(member, data).map((action) =>
                  action === "resend" ? (
                    <button
                      key={action}
                      type="button"
                      className="ac-link"
                      disabled={busy}
                      onClick={() => onResend(member)}
                    >
                      Resend invitation
                    </button>
                  ) : action === "mfa-reset" ? (
                    <button
                      key={action}
                      type="button"
                      className="ac-link"
                      disabled={busy}
                      onClick={() => onConfirm(mfaResetConfirmation(member, onChanged))}
                    >
                      Reset MFA
                    </button>
                  ) : (
                    <button
                      key={action}
                      type="button"
                      className="ac-link uw-team-danger"
                      disabled={busy}
                      onClick={() => onConfirm(removeConfirmation(member, onChanged))}
                    >
                      Remove from trial
                    </button>
                  ),
                )}
              </li>
            ))}
          </ul>
          {data.can_invite && !full && (
            <form
              className="uw-team-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (!ticked.length) return;
                void onInvite(email.trim(), name.trim(), ticked).then((sent) => {
                  if (!sent) return;
                  setName("");
                  setEmail("");
                });
              }}
            >
              <label>
                Colleague's name
                <input required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label>
                Work email
                <input
                  required
                  type="email"
                  maxLength={254}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
              {personas.length > 0 && (
                <PersonaTicks
                  personas={personas}
                  chosen={ticked}
                  onChange={setTicked}
                  legend="Personas: tick one or more"
                />
              )}
              <button
                type="submit"
                className="ac-primary"
                disabled={busy || !ticked.length}
                aria-describedby="uw-team-persona-hint"
              >
                {busy ? "Sending…" : "Send the invitation"}
              </button>
              {personas.length > 0 && (
                <small id="uw-team-persona-hint" className="ac-muted uw-team-hint">
                  {ticked.length
                    ? `${personaList(personas.filter((item) => ticked.includes(item.code)))}. Their rights add up; nobody approves what they prepared. Only you can change them.`
                    : "Tick at least one persona."}
                </small>
              )}
            </form>
          )}
          {data.can_invite && full && (
            <p className="uw-trial-note" role="status">
              Your trial has {data.limit} people, its safety limit. Remove someone to invite another, or{" "}
              <a href="/contact" target="_blank" rel="noopener">
                contact us
              </a>{" "}
              to raise it.
            </p>
          )}
          {data.can_manage && (
            <p className="uw-trial-note">
              Lost your own authenticator? Use a recovery code at sign-in, then Replace authenticator app in My Account
              › Security. Without your recovery codes, contact MDARIX support.
            </p>
          )}
          {!data.can_invite && (
            <p className="uw-trial-note">The person who started this trial can invite colleagues.</p>
          )}
          {message && (
            <div className={`uw-trial-message is-${message.tone}`} role="status">
              <span>{message.text}</span>
              {message.link && <code className="uw-team-link">{message.link}</code>}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
