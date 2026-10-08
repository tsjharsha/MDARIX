import { ApiError, errorMessageFrom } from "../../app/apiClient";

/*
 * File downloads (reports, case records, the risk register) through the same rules as every other call: same-origin
 * session cookie, a time limit, and on failure the server's own message with the request id it logged it under, so
 * a failed export can be quoted to support. A plain link would show the browser a raw JSON error page instead.
 */

/** The file name the server chose (Content-Disposition), or the fallback when it named none. */
export function filenameFrom(disposition: string | null | undefined, fallback: string): string {
  if (!disposition) return fallback;
  const encoded = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(disposition);
  if (encoded) {
    try {
      return sanitizeName(decodeURIComponent(encoded[1].trim().replace(/^"|"$/g, "")), fallback);
    } catch {
      // A malformed encoded name falls through to the plain one.
    }
  }
  const plain = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(disposition);
  return sanitizeName(plain ? (plain[2] ?? plain[1]).trim() : "", fallback);
}

// Only the name itself: never a folder, and never an empty or hidden name.
function sanitizeName(name: string, fallback: string): string {
  const base = name.split(/[\\/]/).pop()?.trim().replace(/^\.+/, "") ?? "";
  return base || fallback;
}

/** The failure of a download as an ApiError: the server's message, its code, and the request id to quote. */
export async function downloadError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => null);
  const detail = (payload as { detail?: unknown } | null)?.detail;
  const structured = detail && typeof detail === "object" && !Array.isArray(detail) ? (detail as any) : {};
  const code = typeof structured.code === "string" ? structured.code : undefined;
  const fromBody = structured.request_id ?? structured.correlation_id;
  const requestId =
    typeof fromBody === "string" && fromBody ? fromBody : (response.headers?.get?.("X-Request-ID") ?? undefined);
  return new ApiError(errorMessageFrom(payload, response.status), response.status, code, requestId);
}

type DownloadOptions = { method?: "GET" | "POST"; fallbackName: string; timeoutMs?: number };

/** Fetch a file the server sends as an attachment and return it with its name (nothing is saved yet). */
export async function fetchFile(
  path: string,
  { method = "GET", fallbackName, timeoutMs = 120_000 }: DownloadOptions,
): Promise<{ blob: Blob; filename: string }> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const response = await fetch(path, {
      method,
      credentials: "same-origin",
      signal: controller.signal,
      headers: { Accept: "application/pdf, text/csv, application/json, */*" },
    });
    if (!response.ok) throw await downloadError(response);
    return {
      blob: await response.blob(),
      filename: filenameFrom(response.headers.get("Content-Disposition"), fallbackName),
    };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw timedOut
      ? new ApiError("MDARIX took too long to prepare the file. Try again in a moment.", 0, "TIMEOUT")
      : new ApiError("MDARIX could not be reached. Check your connection and try again.", 0, "NETWORK_ERROR");
  } finally {
    clearTimeout(timer);
  }
}

/** Download a file and hand it to the browser to save. Returns the name it was saved under. */
export async function downloadFile(path: string, options: DownloadOptions): Promise<string> {
  const { blob, filename } = await fetchFile(path, options);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked after the browser has started the download; revoking at once can cancel it in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
  return filename;
}
