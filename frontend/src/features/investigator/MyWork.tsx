import { useEffect, useState } from "react";
import { ArrowRight, CircleAlert } from "lucide-react";
import type { AppView } from "../../app/router";

type WorkItem = Record<string, string | number | null>;

export function MyWork({ productId, onOpen }: { productId: string; onOpen: (view: AppView) => void }) {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("Assigned to me");
  useEffect(() => {
    if (!productId) return;
    fetch(`/api/v1/products/${productId}/investigations`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("Work could not be loaded"))))
      .then(setItems)
      .catch((reason) => setError(reason.message));
  }, [productId]);
  const visible =
    filter === "All"
      ? items
      : items.filter(
          (item) =>
            filter === "Assigned to me" ||
            String(item.status ?? "")
              .toLowerCase()
              .includes(filter.toLowerCase().split(" ")[0]),
        );
  return (
    <div className="content investigator-work">
      <section className="product-header">
        <div>
          <span className="eyebrow">Investigation workspace</span>
          <h2>My Work</h2>
          <p>Assignments, deadlines, evidence gaps, and reviews for the authenticated tenant.</p>
        </div>
        <button className="primary-action" onClick={() => onOpen("investigations")}>
          Open investigations <ArrowRight size={16} />
        </button>
      </section>
      <nav className="work-tabs" aria-label="My Work filters">
        {[
          "Assigned to me",
          "Created by me",
          "Waiting for evidence",
          "Waiting for review",
          "Due soon",
          "Overdue",
          "All",
        ].map((tab) => (
          <button key={tab} className={filter === tab ? "active" : ""} onClick={() => setFilter(tab)}>
            {tab}
          </button>
        ))}
      </nav>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <section className="panel work-list">
        <div className="section-title">
          <CircleAlert size={18} /> {visible.length} investigation{visible.length === 1 ? "" : "s"}
        </div>
        {visible.length === 0 ? (
          <div className="empty-state">
            <h3>No authorized work matches this view</h3>
            <p>Try another filter or open the investigation list.</p>
          </div>
        ) : (
          visible.map((item, index) => (
            <button className="work-row" key={String(item.id ?? index)} onClick={() => onOpen("investigations")}>
              <span>
                <strong>{String(item.investigation_identifier ?? item.title ?? "Investigation")}</strong>
                <small>
                  {String(item.product_version_identifier ?? item.product_identifier ?? "Product context inherited")}
                </small>
              </span>
              <span>
                <b>{String(item.status ?? "UNKNOWN")}</b>
                <small>{String(item.due_date ?? "Due date not recorded")}</small>
              </span>
              <ArrowRight size={18} aria-hidden="true" />
            </button>
          ))
        )}
      </section>
    </div>
  );
}
