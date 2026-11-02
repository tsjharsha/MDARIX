import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Info,
  Lightbulb,
  ListChecks,
  MapPin,
  NotebookText,
  UserCheck,
} from "lucide-react";
import { BESIDE_YOUR_QMS, PMS_FRAMING } from "./besideYourQms";
import { TRIAL_GUIDE_PATH } from "./trialGuide";
import {
  COVERAGE,
  COVERAGE_MARKETS,
  COVERAGE_NOTE,
  GUIDE_PARTS as PARTS,
  GUIDE_SECTIONS,
  ROLE_SUMMARY,
} from "./userGuide";
import { newPathText } from "../../app/linkTable";
import "./trialGuide.css";
import "./userGuide.css";

/**
 * The step-by-step user guide at /help/user-guide: every screen of the workspace, task by task, with the names of its
 * buttons and fields. The free trial user guide (/help/trial-guide) is the short journey through a trial; this is the
 * manual. It holds no organization data, so it opens without a session and saves as a PDF with the browser's print.
 */
export function UserGuidePage() {
  // An organization on the new navigation opens the guide from Help with ?navigation=new: its paths name the new places.
  const fresh =
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("navigation") === "new";
  const GUIDE_PARTS = fresh ? (JSON.parse(newPathText(JSON.stringify(PARTS))) as typeof PARTS) : PARTS;
  return (
    <div className="help-page tg-page ug-page">
      <a className="app-skip" href="#help-main">
        Skip to content
      </a>
      <header className="help-page-top">
        <a className="auth-brand" href="/" aria-label="MDARIX website">
          <span className="auth-logo" aria-hidden="true">
            M
          </span>
          MDARIX
        </a>
        <span className="tg-top-actions">
          <button type="button" className="tg-print" onClick={() => window.print()}>
            <Download size={15} aria-hidden="true" /> Save as PDF
          </button>
          <a className="help-back" href="/app">
            <ArrowLeft size={15} aria-hidden="true" /> Open MDARIX
          </a>
        </span>
      </header>
      <main id="help-main" tabIndex={-1}>
        <section className="tg-hero ug-hero">
          <p className="help-eyebrow tg-eyebrow">
            <ListChecks size={15} aria-hidden="true" /> Step-by-step user guide
          </p>
          <h1>MDARIX, screen by screen</h1>
          <p className="tg-lede">
            {BESIDE_YOUR_QMS} How to use every part of MDARIX, one task at a time, with the names of the buttons and
            fields exactly as you see them: from signing in to a signed decision, its CAPA and the inspection pack.
          </p>
          <p className="tg-lede">{PMS_FRAMING}</p>
          <p className="ug-other">
            New to a free trial? The{" "}
            <a href={TRIAL_GUIDE_PATH}>
              <NotebookText size={14} aria-hidden="true" /> Free trial user guide
            </a>{" "}
            is the short version: seven steps from the request to the demo.
          </p>
        </section>

        <div className="ug-layout">
          <nav className="ug-contents" aria-label="Contents">
            <p className="ug-contents-title">Contents</p>
            <ol>
              {GUIDE_PARTS.map((part, partIndex) => (
                <li key={part.id}>
                  <a href={`#part-${part.id}`} className="ug-contents-part">
                    {partIndex + 1}. {part.title}
                  </a>
                  <ol>
                    {part.sections.map((section) => (
                      <li key={section.id}>
                        <a href={`#${section.id}`}>{section.title}</a>
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
              <li>
                <a href="#roles" className="ug-contents-part">
                  {GUIDE_PARTS.length + 1}. Who can do what
                </a>
              </li>
              <li>
                <a href="#coverage" className="ug-contents-part">
                  {GUIDE_PARTS.length + 2}. What MDARIX covers
                </a>
              </li>
            </ol>
          </nav>

          <div className="ug-body">
            {GUIDE_PARTS.map((part, partIndex) => (
              <section
                key={part.id}
                id={`part-${part.id}`}
                className="ug-part"
                aria-labelledby={`part-${part.id}-title`}
              >
                <header className="ug-part-head">
                  <p className="ug-part-number">Part {partIndex + 1}</p>
                  <h2 id={`part-${part.id}-title`}>{part.title}</h2>
                  <p>{part.summary}</p>
                </header>
                {part.sections.map((section) => (
                  <article
                    key={section.id}
                    id={section.id}
                    className="ug-section"
                    aria-labelledby={`${section.id}-title`}
                  >
                    <h3 id={`${section.id}-title`}>{section.title}</h3>
                    <p className="ug-where">
                      <MapPin size={14} aria-hidden="true" /> <b>Where:</b> {section.where}
                    </p>
                    <p className="ug-purpose">{section.purpose}</p>
                    {section.tasks.map((task) => (
                      <div key={task.title} className="ug-task">
                        <h4>{task.title}</h4>
                        {task.who && (
                          <p className="ug-who">
                            <UserCheck size={14} aria-hidden="true" /> <b>Who:</b> {task.who}
                          </p>
                        )}
                        <ol className="tg-actions ug-steps">
                          {task.steps.map((step) => (
                            <li key={step}>{step}</li>
                          ))}
                        </ol>
                        {task.result && (
                          <p className="tg-result">
                            <CheckCircle2 size={16} aria-hidden="true" />
                            <span>
                              <b>You will see:</b> {task.result}
                            </span>
                          </p>
                        )}
                        {task.note && (
                          <p className="ug-note">
                            <Info size={16} aria-hidden="true" />
                            <span>{task.note}</span>
                          </p>
                        )}
                      </div>
                    ))}
                    {section.tips?.map((tip) => (
                      <p key={tip} className="tg-tip">
                        <Lightbulb size={16} aria-hidden="true" />
                        <span>{tip}</span>
                      </p>
                    ))}
                  </article>
                ))}
              </section>
            ))}

            <section id="roles" className="ug-part" aria-labelledby="roles-title">
              <header className="ug-part-head">
                <p className="ug-part-number">Part {GUIDE_PARTS.length + 1}</p>
                <h2 id="roles-title">Who can do what</h2>
                <p>
                  Each person has one role, and sees and changes only what it allows. MDARIX checks it again on every
                  action.
                </p>
              </header>
              <table className="ug-roles">
                <thead>
                  <tr>
                    <th scope="col">Role</th>
                    <th scope="col">What it is for</th>
                  </tr>
                </thead>
                <tbody>
                  {ROLE_SUMMARY.map(([role, text]) => (
                    <tr key={role}>
                      <th scope="row">{role}</th>
                      <td>{text}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="tg-small">
                {GUIDE_SECTIONS.length} topics. Names in this guide are the ones on the screen; the records you see are
                your organization's own.
              </p>
            </section>

            <section id="coverage" className="ug-part" aria-labelledby="coverage-title">
              <header className="ug-part-head">
                <p className="ug-part-number">Part {GUIDE_PARTS.length + 2}</p>
                <h2 id="coverage-title">What MDARIX covers</h2>
                <p>
                  By device category, in {COVERAGE_MARKETS}: which reporting clocks, report worksheets and checks apply,
                  and what is not covered yet. Set a product&apos;s category in the products file (column
                  device_category). Starter text, for your regulatory consultant to confirm.
                </p>
              </header>
              {COVERAGE.map((row) => (
                <article key={row.category} className="ug-section" aria-label={row.category}>
                  <h3>{row.category}</h3>
                  <dl className="ug-coverage">
                    <div>
                      <dt>Reporting clocks</dt>
                      <dd>{row.clocks}</dd>
                    </div>
                    <div>
                      <dt>Report worksheets</dt>
                      <dd>{row.worksheets}</dd>
                    </div>
                    <div>
                      <dt>Checks</dt>
                      <dd>{row.checks}</dd>
                    </div>
                    <div>
                      <dt>Not covered yet</dt>
                      <dd>{row.notYet}</dd>
                    </div>
                  </dl>
                </article>
              ))}
              <p className="tg-small">{COVERAGE_NOTE}</p>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
