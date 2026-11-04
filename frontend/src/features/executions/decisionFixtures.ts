/**
 * Test fixtures modelled on execution 3 (task 11.12): the agreement
 * `output_schema` as stored (the provider `{name, schema}` envelope around a
 * lone `class` enum) and the multi-field object the judge actually returned.
 * Text is abridged; no keys or other sensitive data.
 */
export const EXEC3_SCHEMA = {
  name: "requirements-schema",
  description: "A schema for classifying requirements into categories",
  schema: {
    type: "object",
    properties: { class: { type: "string", enum: ["F", "NF"] } },
  },
};

export const EXEC3_DECISION = {
  requirement:
    "The system shall have a MDI form that allows for the viewing of the graph and the data table.",
  debaters_arguments: [
    "Debater 1: This is a Functional requirement because it describes a specific system feature and user capability.",
    "Debater 2: This is a Non-Functional requirement (specifically Usability / Interface) because an MDI form constrains the user interface layout.",
  ],
  moderator_evaluation:
    "While the requirement specifies an MDI form, its primary purpose is to provide the operational capability for users to view data tables and graphs.",
  final_classification: "Functional",
};
