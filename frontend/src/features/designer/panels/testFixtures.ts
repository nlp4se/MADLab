import type { ProviderResponse, TaxonomyResponse } from "@/api";

/**
 * Shared fixtures for the dimension-panel component tests (task 8.4).
 *
 * `SAMPLE_TAXONOMY` is a faithful (abridged) slice of the backend catalog:
 * the sub-dimensions and values the panels render, including at least one
 * non-executable value per dimension so the "under development" badge/warning
 * paths are exercised.
 */
export const SAMPLE_TAXONOMY: TaxonomyResponse = {
  dimensions: [
    {
      key: "participants",
      label: "Participants",
      description: "who debates",
      subdimensions: [
        {
          key: "persona_attributes",
          label: "Persona attributes",
          description: "prompt-designed attribute families",
          selection: "attributes",
          values: [
            { key: "background", label: "Background", description: "identity", default: false, executable: true, icon: null },
            { key: "personality", label: "Personality", description: "behaviour", default: false, executable: true, icon: null },
            { key: "stance", label: "Stance", description: "positioning", default: false, executable: true, icon: null },
          ],
        },
        {
          key: "persona_heterogeneity",
          label: "Persona heterogeneity",
          description: "shared or distinct",
          selection: "single",
          values: [
            { key: "homogeneous", label: "Homogeneous", description: "same persona", default: true, executable: true, icon: null },
            { key: "heterogeneous", label: "Heterogeneous", description: "distinct personas", default: false, executable: true, icon: null },
          ],
        },
        {
          key: "persona_assignment",
          label: "Persona assignment",
          description: "how personas are assigned",
          selection: "single",
          values: [
            { key: "unspecified", label: "Unspecified", description: "none", default: true, executable: true, icon: null },
            { key: "manual", label: "Manually identified", description: "at design time", default: false, executable: true, icon: null },
            { key: "automatic", label: "Automatically identified", description: "at runtime", default: false, executable: false, icon: null },
          ],
        },
        {
          key: "roles",
          label: "Roles",
          description: "functional roles",
          selection: "multi",
          values: [
            { key: "debater", label: "Debater", description: "argues", default: true, executable: true, icon: "role/debater" },
            { key: "judge", label: "Judge", description: "decides", default: false, executable: true, icon: "role/judge" },
            { key: "summarizer", label: "Summarizer", description: "synthesizes", default: false, executable: true, icon: "role/summarizer" },
          ],
        },
        {
          key: "base_model_family",
          label: "Base model family",
          description: "proprietary or public",
          selection: "single",
          values: [
            { key: "closed_weight", label: "Closed-weight", description: "proprietary", default: true, executable: true, icon: null },
            { key: "open_weight", label: "Open-weight", description: "public", default: false, executable: true, icon: null },
          ],
        },
        {
          key: "base_model_heterogeneity",
          label: "Base model heterogeneity",
          description: "one or many models",
          selection: "single",
          values: [
            { key: "homogeneous", label: "Homogeneous", description: "same model", default: true, executable: true, icon: null },
            { key: "heterogeneous", label: "Heterogeneous", description: "different models", default: false, executable: true, icon: null },
          ],
        },
      ],
    },
    {
      key: "interaction",
      label: "Interaction",
      description: "how they talk",
      subdimensions: [
        {
          key: "topology_adaptability",
          label: "Topology adaptability",
          description: "static or dynamic",
          selection: "single",
          values: [
            { key: "static", label: "Static", description: "unchanged", default: true, executable: true, icon: null },
            { key: "dynamic", label: "Dynamic", description: "adapts", default: false, executable: false, icon: null },
          ],
        },
        {
          key: "topology_structure",
          label: "Topology structure",
          description: "overall shape",
          selection: "single",
          values: [
            { key: "fully_connected", label: "Fully connected", description: "all interact", default: true, executable: true, icon: null },
            { key: "grouped", label: "Divided into groups", description: "subgroups", default: false, executable: true, icon: null },
            { key: "structured_network", label: "Structured networks", description: "predefined", default: false, executable: true, icon: null },
          ],
        },
        {
          key: "topology_pattern",
          label: "Topology pattern",
          description: "canonical patterns",
          selection: "single",
          values: [
            { key: "chain", label: "Chain", description: "linear", default: false, executable: true, icon: "topology/chain" },
            { key: "star", label: "Star", description: "centralized", default: false, executable: true, icon: "topology/star" },
          ],
        },
        {
          key: "protocol_mechanism",
          label: "Protocol mechanism",
          description: "turn-taking",
          selection: "single",
          values: [
            { key: "sequential", label: "Sequential", description: "ordered", default: true, executable: true, icon: null },
            { key: "simultaneous", label: "Simultaneous", description: "at once", default: false, executable: true, icon: null },
            { key: "hybrid", label: "Hybrid", description: "both", default: false, executable: true, icon: null },
          ],
        },
        {
          key: "protocol_ordering",
          label: "Protocol ordering",
          description: "speaking order",
          selection: "single",
          values: [
            { key: "fixed", label: "Fixed", description: "predefined", default: true, executable: true, icon: null },
            { key: "randomized", label: "Randomized", description: "random", default: false, executable: true, icon: null },
            { key: "coordinator", label: "Coordinator-selected", description: "coordinator picks", default: false, executable: false, icon: null },
          ],
        },
        {
          key: "format_syntax",
          label: "Format syntax",
          description: "representation",
          selection: "single",
          values: [
            { key: "natural_language", label: "Natural language", description: "text", default: true, executable: true, icon: null },
            { key: "embeddings", label: "Embeddings", description: "vectors", default: false, executable: false, icon: null },
          ],
        },
        {
          key: "format_content",
          label: "Format content",
          description: "content transform",
          selection: "single",
          values: [
            { key: "verbatim", label: "Verbatim", description: "unmodified", default: true, executable: true, icon: null },
            { key: "summarized", label: "Summarized", description: "compressed", default: false, executable: true, icon: null },
            { key: "other", label: "Other", description: "alternative", default: false, executable: false, icon: null },
          ],
        },
        {
          key: "format_content_metadata",
          label: "Format content metadata",
          description: "attached signals",
          selection: "multi",
          values: [
            { key: "confidence", label: "Confidence", description: "certainty", default: false, executable: true, icon: null },
            { key: "uncertainty", label: "Uncertainty", description: "inverse", default: false, executable: true, icon: null },
          ],
        },
        {
          key: "format_memory",
          label: "Format memory",
          description: "context scope",
          selection: "single",
          values: [
            { key: "short_term", label: "Short-term", description: "current debate", default: true, executable: true, icon: null },
            { key: "long_term", label: "Long-term", description: "persistent", default: false, executable: false, icon: null },
          ],
        },
      ],
    },
    {
      key: "agreement",
      label: "Agreement",
      description: "how they decide",
      subdimensions: [
        {
          key: "authority",
          label: "Authority",
          description: "who decides",
          selection: "single",
          values: [
            { key: "collective", label: "Collective", description: "jointly", default: true, executable: true, icon: null },
            { key: "judge_based", label: "Judge-based", description: "a judge", default: false, executable: true, icon: null },
            { key: "hybrid", label: "Hybrid", description: "combined", default: false, executable: true, icon: null },
            { key: "other", label: "Other", description: "non-standard", default: false, executable: true, icon: null },
          ],
        },
        {
          key: "resolution",
          label: "Resolution",
          description: "how it resolves",
          selection: "single",
          values: [
            { key: "majority_vote", label: "Majority vote", description: "most agents", default: true, executable: true, icon: null },
            { key: "argument_evaluation", label: "Argument evaluation", description: "evaluate debate", default: false, executable: true, icon: null },
            { key: "weighted_vote", label: "Weighted vote", description: "weighted", default: false, executable: true, icon: null },
            { key: "scoring", label: "Scoring", description: "scored", default: false, executable: true, icon: null },
            { key: "consensus", label: "Consensus", description: "agreement", default: false, executable: true, icon: null },
          ],
        },
      ],
    },
  ],
  templates: {
    persona_patterns: [
      {
        key: "angel_devil",
        label: "Angel / Devil",
        description: "optimistic vs. critical",
        pair_with: null,
        is_set: true,
        personas: [
          {
            name: "Angel",
            background: "An optimistic advocate.",
            personality: "Encouraging.",
            stance: "Supports the proposal.",
          },
        ],
      },
    ],
    roles: [],
    topologies: [],
  },
  defaults: {
    participants: {
      persona_heterogeneity: "homogeneous",
      persona_assignment: "unspecified",
      base_model_family: "closed_weight",
      base_model_heterogeneity: "homogeneous",
    },
    interaction: {
      topology_adaptability: "static",
      topology_structure: "fully_connected",
      protocol_mechanism: "sequential",
      protocol_ordering: "fixed",
      format_syntax: "natural_language",
      format_content: "verbatim",
      format_memory: "short_term",
    },
    agreement: {
      authority: "collective",
      resolution: "majority_vote",
    },
  },
  under_development: [
    "automatic",
    "dynamic",
    "coordinator",
    "embeddings",
    "other",
    "long_term",
  ],
};

export const SAMPLE_PROVIDERS: ProviderResponse[] = [
  {
    id: 1,
    name: "OpenAI",
    kind: "openai",
    base_url: null,
    models: ["gpt-4o", "gpt-4o-mini"],
    has_key: true,
    created_at: null,
    updated_at: null,
  },
  {
    id: 2,
    name: "Local Ollama",
    kind: "ollama",
    base_url: "http://localhost:11434",
    models: ["llama3", "mistral"],
    has_key: false,
    created_at: null,
    updated_at: null,
  },
];
