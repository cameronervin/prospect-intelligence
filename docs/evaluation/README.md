# Evaluation approach

No metric or dataset is selected in the initial scaffold because evaluation must follow the chosen product outcome.

Before implementing a product feature, define:

1. The user outcome and highest-cost failure.
2. A versioned synthetic dataset containing success, boundary, dependency-failure, and adversarial examples.
3. One MVP north-star metric with a pass threshold and deterministic checks where possible.
4. A LangSmith experiment comparing a named graph/prompt revision against the dataset.
5. Secondary quality, safety, latency, and cost measures.
6. Online trace sampling, alerting, user feedback, privacy, and retention policy.

Record live experiments with dataset version, evaluator version, code revision, prompt/graph revision, experiment URL, aggregate result, slice-level failures, and the stakeholder decision supported by the result. Do not commit raw traces, credentials, or sensitive dataset contents.

