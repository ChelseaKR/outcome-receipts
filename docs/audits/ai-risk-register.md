# AI risk register

System: optional Claude-on-Bedrock narrative drafter. Owner: Chelsea Kelly-Reif.
Default state: disabled. Review cadence: quarterly and on model, prompt, or data
boundary change.

| NIST AI 600-1 risk | Scenario | Control | Residual risk |
|---|---|---|---|
| Confabulation | Model invents or alters a number. | Figures are computed before drafting; allowlist plus raw and post-suppression grounding gates block export. | Low for numeric invention; nonnumeric meaning drift remains Medium. |
| Data privacy | Client data or receipt internals leave the process. | Request builder accepts narrative and scalar displays only; no rows, identifiers, SQL, hashes, or paths; two explicit opt-ins. | Small aggregates may cross the boundary before suppression; organization authorization required. |
| Information integrity | Fluent prose overstates what the metric proves. | Plain-language definitions and caveats travel with receipts; named human approval required. | Medium because numeric grounding cannot prove semantic faithfulness. |
| Harmful bias/homogenization | Draft erases uncertainty or frames outcomes unfairly. | Definitions expose denominators and categories; deterministic drafter remains available; human review. | Medium; no model judge or qualitative fairness metric ships. |
| Human-AI configuration | Operator assumes Bedrock mode is safe by default. | Disabled in config, CLI authorization flag, documented provider retention boundary. | Low if policy gates are preserved. |
| Value-chain integration | Provider model changes behavior under a reused model ID. | Operator pins model ID; any model change requires eval/card/risk review. | Medium where provider version semantics are outside this repo. |

EU AI Act classification: not Annex III high-risk; the drafter does not make an
eligibility, employment, credit, education, law-enforcement, migration, biometric,
or critical-infrastructure decision. It is not a GPAI model provider and performs
no training, so repository training compute is zero. Reviewed 2026-07-12.

Open risks are carried in the residual-risk register. No LLM-as-judge is used; the
calibration gate is N/A until one is introduced.
