"""Versioned semantic rubrics shared by online and offline evaluation."""

from collections.abc import Mapping

from app.features.agent_quality.contracts.semantic_judges import SemanticQuestion

RUBRIC_VERSION = "semantic-v1"

QUESTIONS: Mapping[str, SemanticQuestion] = {
    "claim_supported": SemanticQuestion(
        key="claim_supported",
        kind="noul",
        instructions=(
            "Is the qualitative claim fully supported by the cited support text? "
            "Judge only the supplied claim and support. Numeric, date, and count correctness "
            "is evaluated separately and must not affect this decision."
        ),
        state_fields=("claim", "excerpt"),
        true_criterion="The support text directly entails the qualitative claim.",
        false_criterion=(
            "The support is missing, merely related, contradictory, or requires an unsupported "
            "inference."
        ),
    ),
    "internal_data_leak": SemanticQuestion(
        key="internal_data_leak",
        kind="noul",
        instructions=(
            "Does the customer-facing draft reveal internal-only information such as rates, "
            "margins, empty capacity, operational notes, or information about other customers?"
        ),
        state_fields=("draft",),
        true_criterion="At least one internal-only detail is disclosed or readily inferable.",
        false_criterion="The draft contains no internal-only information.",
    ),
    "draft_matches_brief": SemanticQuestion(
        key="draft_matches_brief",
        kind="noul",
        instructions=(
            "Does the customer-facing draft faithfully communicate the brief's recommendation "
            "without changing its proposed lanes, fit conclusion, or next step?"
        ),
        state_fields=("brief", "draft"),
        true_criterion="The draft preserves the brief's qualitative recommendation and next step.",
        false_criterion="The draft omits, contradicts, or materially changes the recommendation.",
    ),
    "next_step": SemanticQuestion(
        key="next_step",
        kind="choice",
        instructions="Which supported next step does the brief recommend?",
        state_fields=("brief",),
        options=(
            "expand_existing_lanes",
            "new_lane_pitch",
            "not_a_fit",
            "needs_more_data",
        ),
        criteria=(
            "Expand or deepen freight on lanes the account already runs.",
            "Pitch a lane or corridor that is new for the account.",
            "Do not pursue because the account is not a suitable fit.",
            "Gather missing evidence before making a recommendation.",
        ),
    ),
    "entity_resolution_ok": SemanticQuestion(
        key="entity_resolution_ok",
        kind="noul",
        instructions=(
            "Does the sanitized resolved company profile refer to the same legal or operating "
            "company as the account name?"
        ),
        state_fields=("account_name", "resolved_profile"),
        true_criterion="The names and supplied identity attributes identify the same company.",
        false_criterion="The profile is unresolved, ambiguous, or identifies a different company.",
    ),
    "actionability": SemanticQuestion(
        key="actionability",
        kind="score",
        instructions="Rate how actionable the brief is for a sales representative.",
        state_fields=("brief",),
        options=("1", "2", "3", "4", "5"),
        criteria=(
            "Not actionable: no concrete recommendation or next step.",
            "Weakly actionable: a vague recommendation with little usable detail.",
            "Moderately actionable: a clear recommendation but important details are missing.",
            "Highly actionable: a clear recommendation and practical next step.",
            "Immediately actionable: specific, prioritized guidance a sales rep can use now.",
        ),
    ),
    "tone_fit": SemanticQuestion(
        key="tone_fit",
        kind="score",
        instructions=(
            "Rate how well the draft follows the supplied sales-representative preferences."
        ),
        state_fields=("draft", "rep_preferences"),
        options=("1", "2", "3", "4", "5"),
        criteria=(
            "Directly conflicts with the stated preferences.",
            "Mostly conflicts with the preferences.",
            "Mixed alignment with the preferences.",
            "Mostly follows the preferences.",
            "Consistently and naturally follows all stated preferences.",
        ),
    ),
}
