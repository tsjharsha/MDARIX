import { useState } from "react";
import { ClipboardList, FileWarning } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, formatDate, useResource } from "../../customer-admin/shared";
import {
  RISK_FILE_PERIODS,
  plural,
  postMarketText,
  riskFileHeadline,
  riskFilePath,
  riskFileProductPath,
  riskFileStateOf,
  riskFileText,
  type RiskFileBoard,
  type RiskFileDetail,
  type RiskFileProduct,
} from "../riskFile";
import { Hero } from "./boardParts";

/**
 * Records › Risk file input: whether each product's post-market data (complaints with harm or malfunctions, rising
 * trends, decided signals) has reached its risk file (risk reviews of its cases, the risks they assessed, and the
 * reassessments signed decisions asked for). Read only; a person decides what the risk file must say.
 */
export function RiskFileInput() {
  const [days, setDays] = useState(365);
  const [open, setOpen] = useState<RiskFileProduct | null>(null);
  const board = useResource<RiskFileBoard>(riskFilePath(days));
  const headline = riskFileHeadline(board.data);
  return (
    <div className="ac-overview">
      <Hero
        tone={board.data ? headline.tone : "neutral"}
        icon={<FileWarning size={28} />}
        eyebrow="Post-market data and the risk file · ISO 14971 clause 10"
        title={headline.title}
        detail={headline.detail}
      />
      <Panel
        eyebrow="Records"
        title="Risk file input by product"
        source={board}
        action={
          <select aria-label="Period" value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {RISK_FILE_PERIODS.map((period) => (
              <option key={period.days} value={period.days}>
                {period.label}
              </option>
            ))}
          </select>
        }
      >
        {board.data?.items.length ? (
          <ul className="uw-cr-list">
            {board.data.items.map((item) => (
              <RiskFileCard key={item.product.id ?? item.product.name} item={item} onOpen={() => setOpen(item)} />
            ))}
          </ul>
        ) : (
          <Empty title="No products yet" detail="Products with complaints or risks appear here." />
        )}
        {board.data && <p className="ac-note">{board.data.note}</p>}
      </Panel>
      {open?.product.id && <ProductDrawer item={open} days={days} onClose={() => setOpen(null)} />}
    </div>
  );
}

/** One product (exported for its unit test). */
export function RiskFileCard({ item, onOpen }: { item: RiskFileProduct; onOpen: () => void }) {
  const state = riskFileStateOf(item.state);
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${state.tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{item.product.name}</strong>
          {item.product.business_id && <span className="uw-cr-meta">{item.product.business_id}</span>}
          <ToneBadge tone={state.tone} label={state.label} />
        </div>
        <p className="uw-cr-text">
          <strong>Post-market:</strong> {postMarketText(item)}
        </p>
        <p className="uw-cr-text">
          <strong>Risk file:</strong> {riskFileText(item)}
          {item.risk_file.last_review_at ? ` · last review ${formatDate(item.risk_file.last_review_at)}` : ""}
        </p>
        {item.post_market.significant_rises.length > 0 && (
          <p className="uw-cr-meta">Rising: {item.post_market.significant_rises.join("; ")}</p>
        )}
      </div>
      <div className="uw-cr-actions">
        {item.product.id && (
          <button type="button" className="ac-secondary" onClick={onOpen}>
            <ClipboardList size={15} aria-hidden="true" /> Risks and reviews
          </button>
        )}
      </div>
    </li>
  );
}

function ProductDrawer({ item, days, onClose }: { item: RiskFileProduct; days: number; onClose: () => void }) {
  const detail = useResource<RiskFileDetail>(riskFileProductPath(String(item.product.id), days));
  return (
    <Drawer title={`${item.product.name}: risk file input`} onClose={onClose}>
      <Panel title="Risks and the reviews that assessed them" source={detail}>
        {detail.data && <ProductDetail detail={detail.data} />}
      </Panel>
    </Drawer>
  );
}

/** Each risk with the risk reviews that assessed it, the reviews and the open reassessments (exported for its test). */
export function ProductDetail({ detail }: { detail: RiskFileDetail }) {
  return (
    <>
      <section className="ca-drawer-section">
        <h3>Risks ({detail.risks.length})</h3>
        {detail.risks.length ? (
          <ul className="uw-intel-list">
            {detail.risks.map((risk) => (
              <li key={risk.id}>
                <strong>{risk.business_id ?? risk.risk_identifier}</strong> {risk.description}{" "}
                {risk.assessed.length ? (
                  <ToneBadge
                    tone="good"
                    label={`Assessed in ${risk.assessed.map((entry) => entry.case ?? entry.review).join(", ")}`}
                  />
                ) : (
                  <ToneBadge tone="warning" label="Not assessed in the period" />
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No risks of this product are in MDARIX. Import the risk register to link them.</p>
        )}
      </section>
      <section className="ca-drawer-section">
        <h3>Risk reviews ({detail.reviews.length})</h3>
        {detail.reviews.length ? (
          <ul className="uw-intel-list">
            {detail.reviews.map((review, index) => (
              <li key={`${review.review}:${index}`}>
                {review.review} on {review.case} · {(review.outcome ?? "").toLowerCase().replace(/_/g, " ")} ·{" "}
                {plural(review.risks_assessed, "risk")} assessed · {formatDate(review.at)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No completed risk review in the period.</p>
        )}
      </section>
      {detail.reassessments.length > 0 && (
        <section className="ca-drawer-section">
          <h3>Risk reassessments open ({detail.reassessments.length})</h3>
          <ul className="uw-intel-list">
            {detail.reassessments.map((entry, index) => (
              <li key={`${entry.follow_up}:${index}`}>
                {entry.follow_up} on {entry.case}: {entry.title} · {entry.status.toLowerCase().replace(/_/g, " ")}
                {entry.due_at ? ` · due ${formatDate(entry.due_at)}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
