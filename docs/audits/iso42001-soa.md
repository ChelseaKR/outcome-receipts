# ISO/IEC 42001 Statement of Applicability

This is a project-level control map, not a certification claim.

| Control area | Applies | Project implementation or exclusion |
|---|---|---|
| AI policy and accountable ownership | Yes | AGENTS.md invariants, CODEOWNERS, named maintainer, Definition of Done. |
| AI risk and impact assessment | Yes | AI risk register, this impact assessment, quarterly review. |
| Data for AI systems | Yes | Generated data/model cards; request allowlist excludes client rows and identifiers. |
| System lifecycle and change control | Yes | ADRs, SemVer, CHANGELOG, locked deps, model/prompt change gates. |
| Verification and validation | Yes | Synthetic adversarial fixtures, grounding/suppression tests, committed eval. |
| Human oversight | Yes | Named approval is required after the final grounding gate. |
| Third-party/provider management | Yes | Operator-pinned Bedrock model and organization-owned logging/retention review. |
| Model training and fine-tuning | No | Repository performs neither; environmental training metrics are N/A. |
| Production traffic monitoring | No | Local CLI has no hosted service; Bedrock invocation telemetry belongs to the operator account. |
| Incident response | Yes | SECURITY.md and operations runbook with committed postmortem convention. |

Reviewed by Chelsea Kelly-Reif on 2026-07-12. Recheck annually and on an
architecture or provider change.
