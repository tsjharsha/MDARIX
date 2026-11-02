import { useState } from "react";
import { Lock } from "lucide-react";
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

/** The confirmation for giving a colleague another persona, and with it its role (0.10.73). */
export function personaConfirmation(member: TeamMember, persona: TeamPersona, onDone: () => void): Confirmation {
  const name = member.display_name || member.email;
  return {
    title: `Make ${name} a ${persona.label}?`,
    body: `${name} then sees the ${persona.label}'s screens and signs as its role (${persona.sub.toLowerCase()}). Their earlier work stays as it was. Only you can change it again.`,
    confirmLabel: "Change the persona",
    done: `${name} is now a ${persona.label}.`,
    run: async () => {
      await send(`${TEAM_PATH}/${member.id}/persona`, "POST", { persona: persona.code });
      onDone();
    },
  };
}

type Message = { tone: "good" | "bad"; text: string; link?: string };

/**
 * Getting started › Team: who is on the trial, and, for the person who started it, inviting colleagues up to the
 * trial's limit, removing one (the seat is free again), resetting a colleague's MFA, and deciding on the support access
 * MDARIX asks for (backend/app/trial/team.py). A trial has no admin console: these are its owner's.
 */
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
      setMessage({ tone: "bad", text: error instanceof Error ? error.message : "The invitation could not be sent." });
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
        onInvite={(email, name, persona) => invite(TEAM_PATH, { email, display_name: name, persona })}
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
  onInvite: (email: string, name: string, persona: string) => Promise<boolean>;
  onResend: (member: TeamMember) => void;
  onConfirm: (request: Confirmation) => void;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [persona, setPersona] = useState("quality");
  const data = team.data;
  const full = !!data && data.seats_used >= data.limit;
  const personas = data?.personas ?? [];
  const chosen = personas.find((item) => item.code === persona);
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
              Invite as many colleagues as you need. You choose each person's persona, and it is their role: they see
              its screens and sign as it. They cannot change it.
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
                    {member.persona_label}
                    {member.persona_locked && <Lock size={12} aria-label="set by the trial owner" />}
                  </span>
                )}
                <span className={`uw-team-status ${member.status === "ACTIVE" ? "is-active" : ""}`}>
                  {memberStatus(member)}
                </span>
                {data.can_manage && !member.is_owner && personas.length > 0 && (
                  <label className="uw-team-change" title="Set by you: they cannot change it">
                    <Lock size={13} aria-hidden="true" />
                    <span className="ca-sr-only">Persona of {member.display_name || member.email}</span>
                    <select
                      value={member.persona ?? ""}
                      disabled={busy}
                      onChange={(event) => {
                        const next = personas.find((item) => item.code === event.target.value);
                        if (next) onConfirm(personaConfirmation(member, next, onChanged));
                      }}
                    >
                      {personas.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
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
                void onInvite(email.trim(), name.trim(), persona).then((sent) => {
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
                <label>
                  Persona
                  <select
                    value={persona}
                    onChange={(event) => setPersona(event.target.value)}
                    aria-describedby="uw-team-persona-hint"
                  >
                    {personas.map((item) => (
                      <option key={item.code} value={item.code}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button type="submit" className="ac-primary" disabled={busy}>
                {busy ? "Sending…" : "Send the invitation"}
              </button>
              {personas.length > 0 && (
                <small id="uw-team-persona-hint" className="ac-muted uw-team-hint">
                  {chosen ? `${chosen.label}: ${chosen.sub.toLowerCase()}. ` : ""}They see this persona's screens and
                  sign as its role. Only you can change it.
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
