import type { ProviderKind } from "@/api";

/**
 * Human-readable labels for the eight supported provider kinds (Req 8.2):
 * closed-weight (OpenAI, Anthropic, Gemini, Mistral, DeepSeek) and
 * open-weight / local backends (Ollama, vLLM, generic OpenAI-compatible).
 */
export const PROVIDER_KIND_LABELS: Record<ProviderKind, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
  mistral: "Mistral",
  deepseek: "DeepSeek",
  ollama: "Ollama",
  vllm: "vLLM",
  openai_compatible: "OpenAI-compatible",
};

export function providerKindLabel(kind: ProviderKind): string {
  return PROVIDER_KIND_LABELS[kind] ?? kind;
}
