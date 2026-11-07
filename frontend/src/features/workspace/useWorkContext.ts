import { useEffect, useRef, useState } from "react";
import { api } from "../../app/api";
import { ApiError, requestJson } from "../../app/apiClient";
import type { InvestigationSummary, Product, Product360, TemporalMode } from "../../app/types";
import type { CaseLinkState, OpenInvestigationRequest, WorkContext } from "./workspaceContext";
import { defaultTimeContext, preferredInvestigationId } from "./workspaceModel";
import {
  contextBody,
  restoredChoice,
  versionIdentifierFor,
  type ResolvedCase,
  type SavedContext,
} from "./savedContext";

const CONTEXT_PATH = "/api/v1/workspace/context";
// Changes are saved once the person has stopped changing the context for a moment.
const SAVE_DELAY_MS = 800;

const listed = (items: InvestigationSummary[], id: string) => items.some((item) => String(item.id) === id);

/**
 * The investigation the context shows once its product's list is read (exported for its test): the one being opened
 * (a link, a task, a next step, the saved context) when it is listed; null when it is not listed yet and the list was
 * not read again for it (read again: it may have just been opened); else the one already shown when it is listed;
 * else the product's first open one. Never the investigation of a record opened before, and never the first in the
 * list in place of the one being opened.
 */
export const chosenInvestigation = (
  items: InvestigationSummary[],
  pending: string,
  selected: string,
  readAgain: boolean,
): string | null => {
  if (pending && listed(items, pending)) return pending;
  if (pending && !readAgain) return null;
  return preferredInvestigationId(items, selected);
};

/** The version an investigation is shown on: its own (the list's `version_identifier`) when the product has it. */
export const caseVersion = (row: Record<string, unknown>, available: readonly string[] | undefined): string | null => {
  const own = typeof row.version_identifier === "string" ? row.version_identifier : null;
  return own && (available ?? []).includes(own) ? own : null;
};

// A product's default version: its latest.
const defaultVersion = (products: Product[], productId: string) => {
  const available = products.find((product) => product.id === productId)?.available_versions ?? [];
  return available.length ? available[available.length - 1] : null;
};

/**
 * The product / version / investigation / time context every workspace section shares.
 * All reads are tenant-scoped by the server from the session; nothing here names a tenant.
 *
 * The context is kept by the server for the person (GET/PUT /api/v1/workspace/context): on start the saved one is
 * applied when its product, version and case still exist, and every change is saved in the background (a failed save
 * never disturbs the screen). `caseLink` (an address's ?case=INV000147) takes precedence over the saved context.
 */
export function useWorkContext(caseLink?: string | null): WorkContext {
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState("");
  const [version, setVersion] = useState("");
  const [asOf, setAsOf] = useState(() => defaultTimeContext().asOf);
  const [mode, setMode] = useState<TemporalMode>(() => defaultTimeContext().mode);
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  // The product the investigation list was read for (the list lags a product change by one request).
  const [investigationsProduct, setInvestigationsProduct] = useState("");
  const [investigationId, setInvestigationId] = useState("");
  const [investigationsVersion, setInvestigationsVersion] = useState(0);
  const [productsVersion, setProductsVersion] = useState(0);
  // A case to select once the product's investigation list arrives. Applied once, then cleared, so a later refresh
  // keeps the person's own choice instead of going back to the case opened last.
  const pendingSelection = useRef("");
  // The saved version (by id), applied once the product's versions are known.
  const pendingVersionId = useRef<string | null>(null);
  // The pending case the list was read again for, once.
  const rereadFor = useRef("");
  const firstLoad = useRef(true);
  const [started, setStarted] = useState(false);
  const [caseLinkState, setCaseLinkState] = useState<CaseLinkState | null>(() =>
    caseLink ? { id: caseLink, state: "resolving" } : null,
  );
  const [openInvestigationRequest, setOpenInvestigationRequest] = useState<OpenInvestigationRequest | null>(null);
  const [view, setView] = useState<Product360 | null>(null);
  const [state, setState] = useState<WorkContext["state"]>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    const first = firstLoad.current;
    firstLoad.current = false;
    // Only the first load reads the saved context and the case link; a reload after an import keeps the selection.
    const saved: Promise<SavedContext | null> = first
      ? requestJson<SavedContext>(CONTEXT_PATH, { retries: 0 }).catch(() => null)
      : Promise.resolve(null);
    const linked: Promise<ResolvedCase | "not-found" | "failed" | null> =
      first && caseLink
        ? requestJson<ResolvedCase>(`${CONTEXT_PATH}/resolve?investigation=${encodeURIComponent(caseLink)}`).catch(
            (reason) => (reason instanceof ApiError && reason.status === 404 ? "not-found" : "failed"),
          )
        : Promise.resolve(null);
    api<Product[]>("/api/v1/products")
      .then(async (items) => {
        const [savedContext, resolved] = await Promise.all([saved, linked]);
        setProducts(items);
        if (!items.length) setState("empty");
        if (!first) {
          // A reload (after an import) keeps the product the person was working on when it is still there.
          setProductId((selected) => (items.some((item) => item.id === selected) ? selected : (items[0]?.id ?? "")));
          return;
        }
        const fromLink =
          resolved && typeof resolved === "object" && items.some((item) => item.id === String(resolved.product_id))
            ? resolved
            : null;
        if (caseLink)
          setCaseLinkState({
            id: caseLink,
            state: fromLink ? "applied" : resolved === "failed" ? "failed" : "not-found",
          });
        const restore = restoredChoice(savedContext, items);
        if (restore?.mode) setMode(restore.mode);
        if (restore?.asOf) setAsOf(restore.asOf);
        if (fromLink) {
          pendingSelection.current = String(fromLink.investigation_id);
          setInvestigationId(String(fromLink.investigation_id));
          setProductId(String(fromLink.product_id));
        } else if (restore) {
          pendingSelection.current = restore.investigationId ?? "";
          pendingVersionId.current = restore.versionId;
          setProductId(restore.productId);
        } else
          setProductId((selected) => (items.some((item) => item.id === selected) ? selected : (items[0]?.id ?? "")));
        setStarted(true);
      })
      .catch((reason) => {
        setState("error");
        setError(reason instanceof Error ? reason.message : "Products could not be loaded");
        // A case link never stays "opening" when the products could not be read (0.10.92, A4): it is said to fail.
        if (first && caseLink) setCaseLinkState({ id: caseLink, state: "failed" });
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
        // The saved version, once: only when the product still has it.
        const wanted = pendingVersionId.current;
        if (wanted) {
          pendingVersionId.current = null;
          const identifier = versionIdentifierFor(item.versions, wanted);
          const available = products.find((product) => product.id === productId)?.available_versions ?? [];
          if (identifier && identifier !== version && available.includes(identifier)) setVersion(identifier);
        }
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
        const pending = pendingSelection.current;
        // The investigation being opened is not in this read (it was asked for before the investigation existed):
        // read once more rather than fall back to another one (0.10.70).
        if (chosenInvestigation(items, pending, "", rereadFor.current === pending) === null) {
          rereadFor.current = pending;
          setInvestigationsVersion((value) => value + 1);
          return;
        }
        pendingSelection.current = "";
        setInvestigations(items);
        setInvestigationsProduct(productId);
        setInvestigationId((selected) => chosenInvestigation(items, pending, selected, true) ?? "");
      })
      .catch(() => {
        if (!current) return;
        setInvestigations([]);
        setInvestigationsProduct(productId);
      });
    return () => {
      current = false;
    };
  }, [productId, investigationsVersion]);

  // An investigation opened (from a link, a task, a next step, the saved context) shows its own version, the one its
  // complaints carry, never the version a record opened before it was on (0.10.70: the flagship's Rev A investigation
  // read "Rev B"). Once per investigation chosen, so the person may still change the version by hand.
  const versionFor = useRef("");
  useEffect(() => {
    if (!investigationId || versionFor.current === investigationId || investigationsProduct !== productId) return;
    const row = investigations.find((item) => String(item.id) === investigationId);
    if (!row) return;
    versionFor.current = investigationId;
    const wanted = caseVersion(row, products.find((product) => product.id === productId)?.available_versions);
    if (wanted && wanted !== version) {
      pendingVersionId.current = null;
      setVersion(wanted);
    }
  }, [investigationId, investigations, investigationsProduct, productId]);

  // Save the context in the background once it is settled: the start-up context applied, the product's data and its
  // investigation list read. A failed save is ignored; the next change saves again.
  const viewMatches =
    !!view &&
    (!view.product?.id || String(view.product.id) === productId) &&
    (view.selected_version?.version_identifier ?? version) === version;
  const versionId = viewMatches && view?.selected_version?.id ? String(view.selected_version.id) : null;
  const settled = started && !!productId && investigationsProduct === productId && (viewMatches || state === "error");
  const lastSaved = useRef("");
  useEffect(() => {
    if (!settled) return;
    const body = JSON.stringify(contextBody({ productId, versionId, investigationId, mode, asOf }));
    if (body === lastSaved.current) return;
    const timer = window.setTimeout(() => {
      lastSaved.current = body;
      requestJson(CONTEXT_PATH, { method: "PUT", body }).catch(() => {
        lastSaved.current = "";
      });
    }, SAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [settled, productId, versionId, investigationId, mode, asOf]);

  // Choosing another product starts it on its default version and lets its own cases be chosen.
  const chooseProduct = (id: string) => {
    if (id === productId) return;
    pendingSelection.current = "";
    pendingVersionId.current = null;
    const next = defaultVersion(products, id);
    if (next) setVersion(next);
    setInvestigationId("");
    setProductId(id);
  };

  // Choosing a case of another product (from a task, a link) brings its product along.
  const chooseInvestigation = (id: string, forProduct?: string | null) => {
    if (forProduct && forProduct !== productId) {
      pendingVersionId.current = null;
      pendingSelection.current = id;
      const next = defaultVersion(products, forProduct);
      if (next) setVersion(next);
      setInvestigationId(id);
      setProductId(forProduct);
      return;
    }
    setInvestigationId(id);
    if (id && !investigations.some((item) => String(item.id) === id)) {
      // Not in the list yet (just opened): read the list again and select it there.
      pendingSelection.current = id;
      setInvestigationsVersion((value) => value + 1);
    }
  };

  return {
    products,
    productId,
    setProductId: chooseProduct,
    version,
    setVersion,
    asOf,
    setAsOf,
    mode,
    setMode,
    investigations,
    investigationId,
    setInvestigationId: chooseInvestigation,
    refreshInvestigations: (select?: string) => {
      if (select) pendingSelection.current = select;
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
    caseLink: caseLinkState,
    view,
    state,
    error,
  };
}
