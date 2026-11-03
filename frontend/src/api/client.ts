/**
 * Thin, typed fetch client for the MAD backend.
 *
 * The base URL is configurable via the Vite env var `VITE_API_BASE_URL`
 * (default `http://localhost:8000/api`). The backend mounts every resource
 * router under the `/api` prefix (see `backend/app/main.py` `API_PREFIX`), so
 * the default already includes `/api` and resource paths are given relative to
 * it (e.g. `/taxonomy`, `/configs`).
 *
 * Errors are normalized into `ApiError`, which surfaces the backend's
 * structured error envelope when present so callers (and React Query) get a
 * consistent, inspectable failure.
 */

const DEFAULT_BASE_URL = "http://localhost:8000/api";

export function getApiBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const base = (fromEnv ?? DEFAULT_BASE_URL).trim();
  // Normalize away a trailing slash so path joining is predictable.
  return base.replace(/\/+$/, "");
}

/** A normalized API failure carrying the HTTP status and any error payload. */
export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

interface RequestOptions {
  method?: string;
  /** JSON body; serialized and sent with `application/json`. */
  body?: unknown;
  /** Query parameters appended to the URL (undefined values are skipped). */
  query?: Record<string, string | number | boolean | undefined>;
  /** A pre-built body (e.g. FormData); takes precedence over `body`. */
  rawBody?: BodyInit;
  signal?: AbortSignal;
}

function buildUrl(
  path: string,
  query?: RequestOptions["query"],
): string {
  const base = getApiBaseUrl();
  const url = new URL(
    `${base}${path.startsWith("/") ? path : `/${path}`}`,
  );
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  return text.length > 0 ? text : null;
}

function extractErrorMessage(status: number, payload: unknown): string {
  // The backend wraps domain/validation errors in a structured envelope; try a
  // few common shapes before falling back to the status text.
  if (payload && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    const detail = obj.detail ?? obj.message ?? obj.error;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const nested = (detail as Record<string, unknown>).message;
      if (typeof nested === "string") return nested;
    }
  }
  if (typeof payload === "string" && payload.length > 0) return payload;
  return `Request failed with status ${status}`;
}

/** Perform a request and return the parsed JSON body typed as `T`. */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, query, rawBody, signal } = options;

  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined = rawBody;
  if (rawBody === undefined && body !== undefined) {
    headers["content-type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const response = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: payload,
    signal,
  });

  const parsed = await parseBody(response);

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractErrorMessage(response.status, parsed),
      parsed,
    );
  }

  return parsed as T;
}

/** The raw text body of a response plus a filename parsed from any
 * `Content-Disposition` header. Used for file downloads (e.g. artifact export,
 * Req 4.3) where the UI needs the bytes rather than a parsed DTO. */
export interface RawDownload {
  text: string;
  filename: string | null;
}

function parseFilename(disposition: string | null): string | null {
  if (!disposition) return null;
  // Handle both `filename="x.json"` and RFC 5987 `filename*=UTF-8''x.json`.
  const star = /filename\*=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain ? plain[1] : null;
}

/**
 * Perform a GET and return the raw response text (not JSON-parsed) together
 * with any `Content-Disposition` filename. Errors still normalize to
 * `ApiError`.
 */
export async function requestRaw(
  path: string,
  options: Pick<RequestOptions, "query" | "signal"> = {},
): Promise<RawDownload> {
  const response = await fetch(buildUrl(path, options.query), {
    method: "GET",
    signal: options.signal,
  });

  const text = await response.text();
  if (!response.ok) {
    let payload: unknown = text;
    try {
      payload = JSON.parse(text);
    } catch {
      /* keep raw text */
    }
    throw new ApiError(
      response.status,
      extractErrorMessage(response.status, payload),
      payload,
    );
  }

  return {
    text,
    filename: parseFilename(response.headers.get("content-disposition")),
  };
}

export const http = {
  get: <T>(path: string, query?: RequestOptions["query"]) =>
    request<T>(path, { method: "GET", query }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  /** POST a multipart form (e.g. dataset upload); no JSON content-type. */
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", rawBody: form }),
  /** GET a downloadable file as raw text + filename (e.g. config export). */
  getRaw: (path: string, query?: RequestOptions["query"]) =>
    requestRaw(path, { query }),
};
