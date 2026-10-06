import { useEffect, useState } from "react";
import { api } from "../../app/api";
import type { InvestigationSummary, Product, Product360, TemporalMode } from "../../app/types";
import type { OpenInvestigationRequest, WorkContext } from "./workspaceContext";
import { defaultTimeContext, preferredInvestigationId } from "./workspaceModel";

/**
 * The product / version / investigation / time context every workspace section shares.
 * All reads are tenant-scoped by the server from the session; nothing here names a tenant.
 */
export function useWorkContext(): WorkContext {
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState("");
  const [version, setVersion] = useState("");
  const [asOf, setAsOf] = useState(() => defaultTimeContext().asOf);
  const [mode, setMode] = useState<TemporalMode>(() => defaultTimeContext().mode);
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [investigationId, setInvestigationId] = useState("");
  const [investigationsVersion, setInvestigationsVersion] = useState(0);
  const [productsVersion, setProductsVersion] = useState(0);
  const [pendingSelection, setPendingSelection] = useState("");
  const [openInvestigationRequest, setOpenInvestigationRequest] = useState<OpenInvestigationRequest | null>(null);
  const [view, setView] = useState<Product360 | null>(null);
  const [state, setState] = useState<WorkContext["state"]>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Product[]>("/api/v1/products")
      .then((items) => {
        setProducts(items);
        if (!items.length) setState("empty");
        // A reload (after an import) keeps the product the person was working on when it is still there.
        setProductId((selected) => (items.some((item) => item.id === selected) ? selected : (items[0]?.id ?? "")));
      })
      .catch((reason) => {
        setState("error");
        setError(reason instanceof Error ? reason.message : "Products could not be loaded");
      });
  }, [productsVersion]);

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
          preferredInvestigationId(
            items,
            pendingSelection && items.some((item) => String(item.id) === pendingSelection)
              ? pendingSelection
              : selected,
          ),
        );
      })
      .catch(() => current && setInvestigations([]));
    return () => {
      current = false;
    };
  }, [productId, investigationsVersion, pendingSelection]);

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
    refreshInvestigations: (select?: string) => {
      if (select) setPendingSelection(select);
      setInvestigationsVersion((value) => value + 1);
    },
    refreshProducts: () => setProductsVersion((value) => value + 1),
    openInvestigationRequest,
    requestOpenInvestigation: (request: OpenInvestigationRequest) => {
      // The version effect above keeps the version when the product has it, else picks the product's latest.
      setProductId(request.productId);
      if (request.version) setVersion(request.version);
      setOpenInvestigationRequest(request);
    },
    clearOpenInvestigationRequest: () => setOpenInvestigationRequest(null),
    view,
    state,
    error,
  };
}
