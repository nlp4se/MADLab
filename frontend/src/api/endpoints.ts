/**
 * Typed endpoint functions grouped by resource, mapping 1:1 to the backend
 * routers (`backend/app/routers/*`). Each returns the typed DTO from
 * `./types`. These are intentionally plain async functions so they can be used
 * directly or wrapped by React Query hooks in the feature modules.
 */
import { http } from "./client";
import type {
  ConfigCopyRequest,
  ConfigCreateRequest,
  ConfigDetail,
  ConfigImportRequest,
  ConfigSummary,
  ConfigUpdateRequest,
  DatasetPreviewRequest,
  DatasetPreviewResponse,
  DatasetResponse,
  DeleteResponse,
  ExecutionCreateRequest,
  ExecutionDeleteResponse,
  ExecutionDetail,
  ExecutionSummary,
  ProviderCreateRequest,
  ProviderDeleteResponse,
  ProviderResponse,
  ProviderTestRequest,
  ProviderTestResponse,
  ProviderUpdateRequest,
  TaxonomyResponse,
  ValidateRequest,
  ValidationResponse,
} from "./types";

export const taxonomyApi = {
  /** GET /api/taxonomy — the full catalog + templates + defaults (Req 7.4). */
  get: () => http.get<TaxonomyResponse>("/taxonomy"),
};

export const configsApi = {
  list: () => http.get<ConfigSummary[]>("/configs"),
  get: (id: number) => http.get<ConfigDetail>(`/configs/${id}`),
  create: (body: ConfigCreateRequest) =>
    http.post<ConfigDetail>("/configs", body),
  update: (id: number, body: ConfigUpdateRequest) =>
    http.put<ConfigDetail>(`/configs/${id}`, body),
  remove: (id: number) => http.del<DeleteResponse>(`/configs/${id}`),
  copy: (id: number, body: ConfigCopyRequest) =>
    http.post<ConfigDetail>(`/configs/${id}/copy`, body),
  import: (body: ConfigImportRequest) =>
    http.post<ConfigDetail>("/configs/import", body),
  /**
   * GET /api/configs/{id}/export — the backend streams the raw JSON artifact
   * with a `Content-Disposition` attachment header (Req 4.3), so this returns
   * the raw text + filename for a client-side download rather than a DTO.
   */
  export: (id: number) => http.getRaw(`/configs/${id}/export`),
  validate: (body: ValidateRequest) =>
    http.post<ValidationResponse>("/configs/validate", body),
};

export const providersApi = {
  list: () => http.get<ProviderResponse[]>("/providers"),
  create: (body: ProviderCreateRequest) =>
    http.post<ProviderResponse>("/providers", body),
  update: (id: number, body: ProviderUpdateRequest) =>
    http.put<ProviderResponse>(`/providers/${id}`, body),
  remove: (id: number) =>
    http.del<ProviderDeleteResponse>(`/providers/${id}`),
  test: (id: number, body: ProviderTestRequest) =>
    http.post<ProviderTestResponse>(`/providers/${id}/test`, body),
};

export const datasetsApi = {
  get: (id: number) => http.get<DatasetResponse>(`/datasets/${id}`),
  upload: (file: File, name?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    return http.postForm<DatasetResponse>("/datasets", form);
  },
  preview: (id: number, body: DatasetPreviewRequest) =>
    http.post<DatasetPreviewResponse>(`/datasets/${id}/preview`, body),
};

export const executionsApi = {
  list: () => http.get<ExecutionSummary[]>("/executions"),
  get: (id: number) => http.get<ExecutionDetail>(`/executions/${id}`),
  create: (body: ExecutionCreateRequest) =>
    http.post<ExecutionSummary>("/executions", body),
  remove: (id: number) =>
    http.del<ExecutionDeleteResponse>(`/executions/${id}`),
  /**
   * GET /api/executions/{id}/export — the backend returns the full results
   * payload as JSON (Req 11.4). Mirrors the configs export raw-download pattern
   * so the UI can trigger a client-side file download rather than caching a
   * DTO.
   */
  export: (id: number) => http.getRaw(`/executions/${id}/export`),
  /** URL for the SSE progress stream of a running execution (Req 10.5). */
  streamUrl: (id: number) => `/executions/${id}/stream`,
};
