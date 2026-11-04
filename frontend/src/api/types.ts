/**
 * TypeScript types mirroring the backend's response/request DTOs.
 *
 * These are hand-written to match the Pydantic schemas in
 * `backend/app/schemas/*.py`. They are intentionally kept close to the wire
 * shape (not the richer internal `MADConfig`) so the typed client stays a thin,
 * honest contract. Where the backend carries a free-form JSON object
 * (e.g. the full config `artifact`, transcripts, metrics), we use
 * `Record<string, unknown>` and leave richer modelling to the feature that owns
 * it (the designer models the artifact in task 8.3+).
 */

export type JsonObject = Record<string, unknown>;

/* ----------------------------- Taxonomy (7.4) ---------------------------- */

export interface ValueDTO {
  key: string;
  label: string;
  description: string;
  default: boolean;
  executable: boolean;
  icon: string | null;
}

export type SubDimensionSelection = "single" | "multi" | "attributes";

export interface SubDimensionDTO {
  key: string;
  label: string;
  description: string;
  selection: SubDimensionSelection;
  values: ValueDTO[];
}

export interface DimensionDTO {
  key: string;
  label: string;
  description: string;
  subdimensions: SubDimensionDTO[];
}

export interface PersonaFieldSetDTO {
  name: string;
  background: string | null;
  personality: string | null;
  stance: string | null;
}

export interface PersonaPatternDTO {
  key: string;
  label: string;
  description: string;
  pair_with: string | null;
  is_set: boolean;
  personas: PersonaFieldSetDTO[];
}

export interface RoleDTO {
  key: string;
  label: string;
  description: string;
  icon: string | null;
}

export interface TopologyPatternDTO {
  key: string;
  label: string;
  description: string;
  icon: string | null;
}

export interface TemplatesDTO {
  persona_patterns: PersonaPatternDTO[];
  roles: RoleDTO[];
  topologies: TopologyPatternDTO[];
}

export interface TaxonomyResponse {
  dimensions: DimensionDTO[];
  templates: TemplatesDTO;
  /** `{ dimension: { subdimension: value_key } }` defaults. */
  defaults: Record<string, Record<string, string>>;
  /** Keys of all non-executable ("under development") values. */
  under_development: string[];
}

/* -------------------------- Configurations (5) --------------------------- */

export interface ConfigSummaryAttributes {
  participant_count: number;
  topology_structure: string;
  topology_pattern: string | null;
  protocol_mechanism: string;
  authority: string;
  resolution: string;
  under_development: boolean;
}

export interface ConfigSummary {
  id: number;
  name: string;
  description: string | null;
  schema_version: string;
  created_at: string | null;
  updated_at: string | null;
  is_builtin: boolean;
  attributes: ConfigSummaryAttributes;
}

export interface ConfigDetail {
  id: number;
  name: string;
  description: string | null;
  schema_version: string;
  created_at: string | null;
  updated_at: string | null;
  is_builtin: boolean;
  artifact: JsonObject;
  under_development: string[];
}

export interface ConfigCreateRequest {
  name?: string | null;
  description?: string | null;
  artifact?: JsonObject | null;
}

export interface ConfigUpdateRequest {
  name?: string | null;
  description?: string | null;
  artifact?: JsonObject | null;
}

export interface ConfigCopyRequest {
  name?: string | null;
  description?: string | null;
}

export interface ConfigImportRequest {
  artifact: JsonObject;
  name?: string | null;
  description?: string | null;
}

export interface ValidateRequest {
  artifact: JsonObject;
}

export interface FieldError {
  field: string;
  message: string;
}

export interface ValidationResponse {
  valid: boolean;
  errors: FieldError[];
  under_development: string[];
}

export interface DeleteResponse {
  id: number;
  deleted: boolean;
  referencing_executions: number;
}

/* ----------------------------- Providers (8) ----------------------------- */

export type ProviderKind =
  | "openai"
  | "anthropic"
  | "gemini"
  | "mistral"
  | "deepseek"
  | "ollama"
  | "vllm"
  | "openai_compatible";

export const PROVIDER_KINDS: ProviderKind[] = [
  "openai",
  "anthropic",
  "gemini",
  "mistral",
  "deepseek",
  "ollama",
  "vllm",
  "openai_compatible",
];

/** Base-model family of a provider (task 11.9). */
export type ProviderFamily = "open_weight" | "closed_weight";

export interface ProviderResponse {
  id: number;
  name: string;
  kind: ProviderKind;
  base_url: string | null;
  models: string[];
  /**
   * Effective base-model family: fixed by kind, or the stored choice (else the
   * kind default) for mixed kinds (mistral, openai_compatible).
   */
  family: ProviderFamily;
  /** The only key-related signal; the key itself is never returned (Req 8.4). */
  has_key: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProviderCreateRequest {
  name: string;
  kind: ProviderKind;
  base_url?: string | null;
  models?: string[];
  /** Write-only; encrypted at rest, never echoed back (Req 8.4). */
  api_key?: string | null;
  /** Only meaningful for mixed kinds; a contradicting value is a 422. */
  family?: ProviderFamily | null;
}

export interface ProviderUpdateRequest {
  name?: string | null;
  kind?: ProviderKind | null;
  base_url?: string | null;
  models?: string[] | null;
  /**
   * Mixed kinds only: omit to keep (re-derived when the kind changes), `null`
   * resets to the kind default. A value contradicting a fixed kind is a 422.
   */
  family?: ProviderFamily | null;
  /**
   * Write-only, tri-state: omit to keep the stored key, send a string to
   * replace it, send `null` to clear it (Req 8.4).
   */
  api_key?: string | null;
}

export interface ProviderTestRequest {
  model?: string | null;
}

export interface ProviderTestResponse {
  ok: boolean;
  message: string;
  model: string | null;
  latency_s: number | null;
}

export interface ProviderDeleteResponse {
  id: number;
  deleted: boolean;
}

/* ----------------------------- Datasets (10) ----------------------------- */

export interface DatasetResponse {
  id: number;
  name: string;
  original_filename: string;
  columns: string[];
  row_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface DatasetPreviewRequest {
  mapping: Record<string, string>;
  config_id?: number | null;
  template?: string | null;
  row_index?: number;
}

export interface DatasetPreviewResponse {
  row_index: number;
  resolved_input: string;
  instance: JsonObject;
}

/* -------------------------- Design assistant (11.1) ---------------------- */

export interface AssistantMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AssistantDesignRequest {
  /** DB id of the provider to call (chosen per request in the chat panel). */
  provider_id: number;
  /** Model key on that provider (chosen per request; never hardcoded). */
  model: string;
  /** The new user message. */
  message: string;
  /** Prior conversation turns, oldest first. */
  history?: AssistantMessage[];
  /** The MAD config currently being edited, or null for a fresh design. */
  artifact?: JsonObject | null;
}

export interface AssistantDesignResponse {
  /**
   * `"question"` → the model needs clarification (`artifact` is null);
   * `"proposal"` → `message` explains and `artifact` is a full, validated
   * MADConfig JSON.
   */
  mode: "question" | "proposal";
  message: string;
  artifact: JsonObject | null;
  /** Keys of any non-executable taxonomy selections in a proposed artifact. */
  under_development: string[];
}

/* ---------------------------- Executions (11) ---------------------------- */

export interface BatchInput {
  dataset_id: number;
  mapping: Record<string, string>;
  ground_truth_column?: string | null;
  limit?: number | null;
}

export interface ExecutionCreateRequest {
  config_id: number;
  input?: JsonObject | null;
  batch?: BatchInput | null;
}

export type ExecutionStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface ExecutionSummary {
  id: number;
  config_id: number | null;
  config_name: string | null;
  input_mode: string;
  status: string;
  progress: number;
  instance_count: number;
  completed_count: number;
  error_count: number;
  metrics: JsonObject | null;
  created_at: string | null;
  updated_at: string | null;
  /** When the job started / reached a terminal status (UTC); null on old runs. */
  started_at?: string | null;
  finished_at?: string | null;
  /** Execution time + token usage of the run (task 11.18). */
  summary?: RunSummary | null;
}

/** Token / time totals over every model call of one instance (task 11.18). */
export interface InstanceUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number | null;
  /** Summed per-call model latency in seconds; null when none reported. */
  model_time_s: number | null;
  calls: number;
}

/** Instance counts: completed succeeded, failed errored, the rest pending. */
export interface InstanceCounts {
  total: number;
  completed: number;
  failed: number;
}

/**
 * Run summary (task 11.18). `wall_time_s` is the elapsed clock time
 * (null without a start timestamp); `model_time_s` sums every call's latency.
 */
export interface RunSummary {
  wall_time_s: number | null;
  model_time_s: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number | null;
  calls: number;
  instances: InstanceCounts;
}

export interface ExecutionInstanceResult {
  instance_index: number;
  resolved_input: JsonObject;
  transcript: JsonObject | null;
  final_decision: JsonObject | null;
  ground_truth: string | null;
  metrics: JsonObject | null;
  error: string | null;
  /** Token totals of the instance's model calls; null without a transcript. */
  usage?: InstanceUsage | null;
  /** Wall-clock seconds of the debate; null when not recorded. */
  duration_s?: number | null;
}

export interface ExecutionDetail extends ExecutionSummary {
  config_snapshot: JsonObject;
  input_ref: JsonObject;
  instances: ExecutionInstanceResult[];
}

export interface ExecutionDeleteResponse {
  id: number;
  deleted: boolean;
}
