import { useEffect, useState } from "react";
import { api } from "../../app/api";
import type { InvestigationSummary, Product, Product360, TemporalMode } from "../../app/types";
import type { WorkContext } from "./workspaceContext";

/**
 * The product / version / investigation / time context every workspace section shares.
 * All reads are tenant-scoped by the server from the session; nothing here names a tenant.
 */
export function useWorkContext(): WorkContext {
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState("");
  const [version, setVersion] = useState("");
  const [asOf, setAsOf] = useState("2026-02-15");
  const [mode, setMode] = useState<TemporalMode>("event");
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [investigationId, setInvestigationId] = useState("");
  const [view, setView] = useState<Product360 | null>(null);
  const [state, setState] = useState<WorkContext["state"]>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Product[]>("/api/v1/products")
      .then((items) => {
        setProducts(items);
        if (!items.length) setState("empty");
        setProductId(items[0]?.id ?? "");
      })
      .catch((reason) => {
        setState("error");
        setError(reason instanceof Error ? reason.message : "Products could not be loaded");
      });
  }, []);

  // Keep the selected version one the product actually has, so the selector and the data always agree.
  useEffect(() => {
    const available = products.find((product) => product.id === productId)?.available_versions ?? [];
    if (available.length && !available.includes(version)) setVersion(available[available.length - 1]);
    if (!available.length && !version) setVersion("D");
  }, [productId, products]);

  useEffect(() => {
    if (!productId || !version) return;
    let current = true;
    const params = new URLSearchParams({ version_id: version, as_of: `${asOf}T00:00:00Z`, mode });
    api<Product360>(`/api/v1/products/${productId}/product-360?${params}`)
      .then((item) => {
        if (!current) return;
        setView(item);
        setState("ready");
        setError("");
      })
      .catch((reason) => {
        if (!current) return;
        setState("error");
        setError(reason instanceof Error ? reason.message : "Product data could not be loaded");
      });
    return () => {
      current = false;
    };
  }, [productId, version, asOf, mode]);

  useEffect(() => {
    if (!productId) return;
    let current = true;
    api<InvestigationSummary[]>(`/api/v1/products/${productId}/investigations`)
      .then((items) => {
        if (!current) return;
        setInvestigations(items);
        setInvestigationId((selected) =>
          items.some((item) => item.id === selected) ? selected : String(items[0]?.id ?? ""),
        );
      })
      .catch(() => current && setInvestigations([]));
    return () => {
      current = false;
    };
  }, [productId]);

  return {
    products,
    productId,
    setProductId,
    version,
    setVersion,
    asOf,
    setAsOf,
    mode,
    setMode,
    investigations,
    investigationId,
    setInvestigationId,
    view,
    state,
    error,
  };
}
