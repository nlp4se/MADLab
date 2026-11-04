"""The assistant system prompt teaches the participant-scope invariants (task 11.6)."""

from app.services.assistant_prompt import build_system_prompt


def test_prompt_states_participant_scope_rules():
    prompt = build_system_prompt()
    # Persona assignment gates personas.
    assert "`unspecified` = NO personas" in prompt
    # Homogeneous persona = one shared persona for debaters.
    assert "role has the SAME persona" in prompt
    # Homogeneous base model = same provider/model on every node.
    assert "`homogeneous` = EVERY node has the same" in prompt
    assert "`provider_id` / `model_key`. Different models" in prompt
    assert "`system_prompt` is per node" in prompt


def test_prompt_states_family_is_derived():
    """Task 11.9: family comes from the provider and is never chosen."""
    prompt = build_system_prompt()
    assert "`base_model.family` (open/closed weight) is DERIVED" in prompt
    assert "closed_weight|open_weight" not in prompt


def test_prompt_states_interaction_and_agreement_rules():
    """Task 11.7: the invariants the designer enforces for protocol/agreement."""
    prompt = build_system_prompt()
    assert "A `hybrid` mechanism REQUIRES at least one phase" in prompt
    assert "a participant left out of `order` never speaks" in prompt
    assert "`argument_evaluation` needs a judge" in prompt
    assert "NEVER with `collective`" in prompt
    assert "With `judge_based` the judge's reply IS the decision" in prompt
    assert "needs a node with the `summarizer`" in prompt
    assert "do not propose `grouped`" in prompt
