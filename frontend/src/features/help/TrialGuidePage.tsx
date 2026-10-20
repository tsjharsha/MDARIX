import { ArrowLeft, BookOpen, CheckCircle2, Clock3, Download, Info, Lightbulb, Signpost } from "lucide-react";
import { AFTER_THE_TRIAL, GUIDE_STEPS, TRIAL_FACTS } from "./trialGuide";
import {
  AFTER_YOUR_TRIAL,
  CHANGES_COLUMNS,
  CHANGES_TITLE,
  CUSTOMER_ADMINISTRATOR,
  MVP_STEPS,
  PRICE,
  REAL_DATA_NOTICE,
  START_LEDE,
  START_TITLE,
  TRIAL_TO_MVP,
  WHAT_WE_NEED,
} from "./trialNextSteps";
import { GuideScene, JourneyHero } from "./TrialGuideVisuals";
import "./trialGuide.css";

/**
 * The free trial user guide at /help/trial-guide: the journey from the first visit to the one-to-one demo, one step at
 * a time, each with a picture of the screen it happens on, then After your trial: the pilot, in the words of the
 * workspace's Next steps page (trialNextSteps.ts). It holds no organization data, so it opens without a
 * session: it can be read before the first sign-in, linked from the sign-up confirmation and Getting started, and
 * saved as a PDF (the browser's print) to attach to an email.
 */
export function TrialGuidePage() {
  return (
    <div className="help-page tg-page">
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
        <section className="tg-hero">
          <p className="help-eyebrow tg-eyebrow">
            <BookOpen size={15} aria-hidden="true" /> Free trial user guide
          </p>
          <h1>Your MDARIX free trial, step by step</h1>
          <p className="tg-lede">
            Seven steps take you from the first visit to a one-to-one demo on your own trial: request it, sign in, bring
            two colleagues, see the sample data tell the story, run the same checks on your own export, tell us what you
            think, and book the demo.
          </p>
          <JourneyHero titles={GUIDE_STEPS.map((step) => step.title)} />
          <ul className="tg-facts" aria-label="The free trial">
            {TRIAL_FACTS.map(([value, label]) => (
              <li key={value}>
                <strong>{value}</strong>
                <span>{label}</span>
              </li>
            ))}
          </ul>
        </section>

        <nav className="tg-contents" aria-label="Steps">
          <ol>
            {GUIDE_STEPS.map((step, index) => (
              <li key={step.key}>
                <a href={`#step-${index + 1}`}>
                  <span>{index + 1}</span> {step.title}
                </a>
              </li>
            ))}
            <li>
              <a href="#after-your-trial">
                <span aria-hidden="true">
                  <Signpost size={13} />
                </span>{" "}
                {AFTER_YOUR_TRIAL.title}
              </a>
            </li>
          </ol>
        </nav>

        <div className="tg-steps">
          {GUIDE_STEPS.map((step, index) => (
            <section
              key={step.key}
              id={`step-${index + 1}`}
              className="tg-step"
              aria-labelledby={`step-${index + 1}-title`}
            >
              <div className="tg-step-picture">
                <GuideScene step={step.key} />
              </div>
              <div className="tg-step-text">
                <p className="tg-step-number">
                  Step {index + 1} of {GUIDE_STEPS.length}
                  <span>
                    <Clock3 size={13} aria-hidden="true" /> {step.time}
                  </span>
                </p>
                <h2 id={`step-${index + 1}-title`}>{step.title}</h2>
                <p className="tg-why">{step.why}</p>
                <ol className="tg-actions">
                  {step.actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ol>
                <p className="tg-result">
                  <CheckCircle2 size={16} aria-hidden="true" />
                  <span>
                    <b>You will see:</b> {step.result}
                  </span>
                </p>
                {step.tip && (
                  <p className="tg-tip">
                    <Lightbulb size={16} aria-hidden="true" />
                    <span>{step.tip}</span>
                  </p>
                )}
              </div>
            </section>
          ))}
        </div>

        <AfterYourTrial />

        <section className="tg-after" aria-labelledby="tg-after-title">
          <h2 id="tg-after-title">When the 30 days are over</h2>
          <ul>
            {AFTER_THE_TRIAL.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="tg-small">
            The pictures in this guide are illustrations of the screens; names and numbers in them are examples.
          </p>
        </section>
      </main>
    </div>
  );
}

/** After your trial: how the trial becomes a pilot on the organization's real data, from the Next steps text. */
export function AfterYourTrial() {
  return (
    <section id="after-your-trial" className="tg-chapter" aria-labelledby="after-your-trial-title">
      <p className="tg-step-number">After the seven steps</p>
      <h2 id="after-your-trial-title">{AFTER_YOUR_TRIAL.title}</h2>
      <p className="tg-why">{AFTER_YOUR_TRIAL.lede}</p>
      <p className="tg-tip">
        <Info size={16} aria-hidden="true" />
        <span>
          <b>{REAL_DATA_NOTICE.title}.</b> {REAL_DATA_NOTICE.text}
        </span>
      </p>

      <h3>{CHANGES_TITLE}</h3>
      <table className="tg-changes">
        <thead>
          <tr>
            <td />
            <th scope="col">{CHANGES_COLUMNS.trial}</th>
            <th scope="col">{CHANGES_COLUMNS.mvp}</th>
          </tr>
        </thead>
        <tbody>
          {TRIAL_TO_MVP.map((row) => (
            <tr key={row.aspect}>
              <th scope="row">{row.aspect}</th>
              <td data-label={CHANGES_COLUMNS.trial}>{row.trial}</td>
              <td data-label={CHANGES_COLUMNS.mvp}>{row.mvp}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>{START_TITLE}</h3>
      <p className="tg-why">{START_LEDE}</p>
      <ol className="tg-mvp-steps">
        {MVP_STEPS.map((step) => (
          <li key={step.title}>
            <span>{step.label}</span>
            <strong>{step.title}</strong>
            <p>{step.text}</p>
          </li>
        ))}
      </ol>

      <div className="tg-mvp-pair">
        <div>
          <h3>{CUSTOMER_ADMINISTRATOR.title}</h3>
          <p>{CUSTOMER_ADMINISTRATOR.lede}</p>
          <ul>
            {CUSTOMER_ADMINISTRATOR.duties.map((duty) => (
              <li key={duty}>{duty}</li>
            ))}
          </ul>
          <p className="tg-small">{CUSTOMER_ADMINISTRATOR.note}</p>
        </div>
        <div>
          <h3>{WHAT_WE_NEED.title}</h3>
          <ul>
            {WHAT_WE_NEED.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>

      <h3>{PRICE.title}</h3>
      <p>{PRICE.text}</p>
      <p className="tg-result">
        <CheckCircle2 size={16} aria-hidden="true" />
        <span>{AFTER_YOUR_TRIAL.where}</span>
      </p>
    </section>
  );
}
