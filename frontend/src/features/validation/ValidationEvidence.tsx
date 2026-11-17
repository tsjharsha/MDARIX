import { useState, type ChangeEvent } from "react";
import { FileCheck2, FlaskConical, ListChecks, SearchX, Upload } from "lucide-react";
import { Panel, StatTile, ToneBadge } from "../admin/console/charts";
import type { Tone } from "../admin/console/dashboardModel";
import { Table, useResource } from "../customer-admin/shared";
import { describeError, requestJson } from "../../app/apiClient";
import { formatDateTime } from "../../app/dates";
import { downloadFile } from "../reports/download";
import "./validation.css";

/*
 * Validation evidence (E2): each requirement, the automated tests that cover it and their last recorded result, the
 * gaps, and the release validation pack. The server reads it for an administrator, a free trial's owner and a
 * platform administrator only (backend/app/access/validation_evidence.py). Results come only from a recorded test
 * run; without one the screen says "No run recorded". It supports a customer's own validation; it never says that
 * MDARIX or a release is validated.
 */

export const VALIDATION_EVIDENCE_PATH = "/api/v1/admin/validation-evidence";
const RECORD_PATH = "/api/v1/platform-admin/validation-runs";
export const NO_RUN = "No run recorded";

type NamedTest = { file: string; result: string; tests: number };
export type EvidenceRow = {
  req_id: string;
  class: string;
  text: string;
  named_tests: NamedTest[];
  linked_tests: { id: string; result: string }[];
  scenarios_passed: string;
  result: string;
  gap: boolean;
};
export type TestRun = {
  commit: string;
  tree: string;
  ran_at: string | null;
  uploaded_at: string | null;
  passed: number;
  failed: number;
  skipped: number;
  file_name: string;
};
export type ValidationEvidenceData = {
  requirements: EvidenceRow[];
  counts: { requirements: number; with_tests: number; gaps: number; passed: number; failed: number; not_run: number };
  protocol: { id: string; signed: boolean; expected_results: number; expected_confirmed: number };
  release: string;
  run: TestRun | null;
};

const TONES: Record<string, Tone> = {
  Passed: "good",
  Failed: "critical",
  "No test": "warning",
};

/** A result as a badge: the tone never carries the meaning alone (the words are always there). */
export const resultTone = (result: string): Tone => TONES[result] ?? "neutral";

/** The run the results come from, in one line; "No run recorded" when there is none. */
export function runLine(run: TestRun | null): string {
  if (!run) return NO_RUN;
  const when = run.ran_at ?? run.uploaded_at;
  return [
    `Last run ${when ? formatDateTime(when) : "(time not recorded)"}`,
    `commit ${run.commit.slice(0, 8)}`,
    `${run.passed} passed, ${run.failed} failed, ${run.skipped} skipped`,
  ].join(" · ");
}

type Filter = "All" | "Gaps" | "Failed";
const FILTERS: Filter[] = ["All", "Gaps", "Failed"];

/** The requirements a filter keeps. */
export const filterRows = (rows: EvidenceRow[], filter: Filter) =>
  filter === "Gaps"
    ? rows.filter((row) => row.gap)
    : filter === "Failed"
      ? rows.filter((row) => row.result === "Failed")
      : rows;

function Tests({ row }: { row: EvidenceRow }) {
  if (row.gap) return <span className="ve-gap">No test covers this requirement yet</span>;
  return (
    <ul className="ve-tests">
      {row.named_tests.map((test) => (
        <li key={test.file}>
          <code>{test.file.replace(/^tests\//, "")}</code>
          {test.tests > 0 && <span className="ac-muted"> · {test.tests} tests run</span>}
        </li>
      ))}
      {row.linked_tests.length > 0 && (
        <li className="ac-muted">
          {row.linked_tests.length} tagged {row.linked_tests.length === 1 ? "test" : "tests"} · scenarios passed{" "}
          {row.scenarios_passed}
        </li>
      )}
    </ul>
  );
}

const columns = [
  {
    key: "req_id",
    label: "Requirement",
    render: (row: EvidenceRow) => (
      <span className="ve-req">
        <strong>{row.req_id}</strong>
        <span className="ac-muted">Class {row.class}</span>
      </span>
    ),
  },
  { key: "text", label: "What it requires", render: (row: EvidenceRow) => <span className="ve-text">{row.text}</span> },
  { key: "tests", label: "Tests that cover it", render: (row: EvidenceRow) => <Tests row={row} /> },
  {
    key: "result",
    label: "Last result",
    render: (row: EvidenceRow) => (
      <ToneBadge tone={resultTone(row.result)} label={row.gap ? "Gap: no test" : row.result} />
    ),
  },
];

/** A platform administrator records a test run: the JUnit XML of a pytest run with the requirement markers. */
function RecordRun({ onRecorded }: { onRecorded: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const saved = await requestJson<{ passed: number; failed: number }>(RECORD_PATH, {
        method: "POST",
        body,
        timeoutMs: 120_000,
      });
      onRecorded(`Test run recorded: ${saved.passed} passed, ${saved.failed} failed.`);
    } catch (failure) {
      setError(describeError(failure, "The test run was not recorded."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="ve-record">
      <label className="ac-secondary">
        <Upload size={16} aria-hidden="true" />
        {busy ? "Recording…" : "Record a test run (JUnit XML)"}
        <input type="file" accept=".xml,application/xml,text/xml" onChange={upload} disabled={busy} hidden />
      </label>
      {error && (
        <span role="alert" className="ve-error">
          {error}
        </span>
      )}
    </span>
  );
}

export function ValidationEvidence({ canRecord = false }: { canRecord?: boolean }) {
  const evidence = useResource<ValidationEvidenceData>(VALIDATION_EVIDENCE_PATH);
  const [filter, setFilter] = useState<Filter>("All");
  const [note, setNote] = useState("");
  const [downloading, setDownloading] = useState(false);
  const data = evidence.data;
  const download = async () => {
    setDownloading(true);
    setNote("");
    try {
      const name = await downloadFile(`${VALIDATION_EVIDENCE_PATH}/pack`, {
        fallbackName: "mdarix-validation-pack.zip",
      });
      setNote(`Downloaded ${name}.`);
    } catch (failure) {
      setNote(describeError(failure, "The validation pack could not be prepared."));
    } finally {
      setDownloading(false);
    }
  };
  const counts = data?.counts;
  const rows = data ? filterRows(data.requirements, filter) : [];
  return (
    <div className="ve">
      <Panel eyebrow="Evidence to support your validation" title="Validation evidence" source={evidence}>
        <p className="ve-lead">
          Each MDARIX requirement, the automated tests that cover it and their last recorded result. Use it as input to
          your own computer system validation; it does not validate your use of MDARIX.
        </p>
        <section className="ac-stats ve-stats" aria-label="Validation evidence at a glance">
          <StatTile
            label="Requirements"
            value={counts?.requirements ?? null}
            detail={`${counts?.with_tests ?? 0} covered by a test`}
            icon={<ListChecks size={18} />}
          />
          <StatTile
            label="Gaps"
            value={counts?.gaps ?? null}
            detail="Requirements without a test"
            icon={<SearchX size={18} />}
            tone={counts?.gaps ? "warning" : "good"}
            onOpen={() => setFilter("Gaps")}
          />
          <StatTile
            label="Last result"
            value={data?.run ? `${counts?.passed ?? 0} passed` : NO_RUN}
            detail={
              data?.run ? `${counts?.failed ?? 0} failed · ${counts?.not_run ?? 0} not in the run` : "No results yet"
            }
            icon={<FlaskConical size={18} />}
            tone={!data?.run ? "neutral" : counts?.failed ? "critical" : "good"}
          />
          <StatTile
            label="OQ protocol"
            value={data?.protocol.signed ? "Signed" : "Not yet signed"}
            detail={`Expected results confirmed: ${data?.protocol.expected_confirmed ?? 0} of ${data?.protocol.expected_results ?? 0}`}
            icon={<FileCheck2 size={18} />}
            tone={data?.protocol.signed ? "good" : "warning"}
          />
        </section>
        <div className="ve-bar">
          <span className="ve-run">
            <strong>{data?.run ? "Results from the recorded run" : NO_RUN}</strong>
            <span className="ac-muted">
              {data?.run ? runLine(data.run) : "Results appear here once a test run is recorded."}
            </span>
          </span>
          <span className="ve-actions">
            {canRecord && (
              <RecordRun
                onRecorded={(message) => {
                  setNote(message);
                  evidence.reload();
                }}
              />
            )}
            <button type="button" className="ac-primary" onClick={download} disabled={downloading}>
              {downloading
                ? "Preparing the pack…"
                : `Download the release validation pack${data?.release ? ` (${data.release})` : ""}`}
            </button>
          </span>
        </div>
        {note && (
          <p className="ve-note" role="status">
            {note}
          </p>
        )}
        <p className="ac-muted ve-small">
          The pack is generated now from the requirements, the recorded run and the OQ protocol. Every document in it is
          marked as development results until the protocol is signed and the release is approved.
        </p>
        <div className="ve-filters" role="group" aria-label="Show requirements">
          {FILTERS.map((name) => (
            <button
              key={name}
              type="button"
              className={filter === name ? "ac-primary" : "ac-secondary"}
              aria-pressed={filter === name}
              onClick={() => setFilter(name)}
            >
              {name}
              {name === "Gaps" && counts
                ? ` (${counts.gaps})`
                : name === "Failed" && counts
                  ? ` (${counts.failed})`
                  : ""}
            </button>
          ))}
        </div>
        <Table
          caption="Requirements and their tests"
          rows={rows}
          columns={columns}
          rowKey={(row) => row.req_id}
          pageSize={8}
          pageNoun="requirements"
          empty={{
            title: filter === "Gaps" ? "No gaps" : "Nothing failed",
            detail:
              filter === "Gaps" ? "Every requirement has a test." : "No requirement has a failed test in the run.",
          }}
        />
      </Panel>
    </div>
  );
}
