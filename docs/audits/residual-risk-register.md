# Residual risk register

| Risk | Severity | Owner | Treatment and review |
|---|---|---|---|
| Nonnumeric model prose changes the meaning of a receipted figure. | Medium | Report approver | Review definitions, caveats, and narrative; use deterministic drafting under no-cloud or high-sensitivity policy. Quarterly and model/prompt change. |
| Small aggregate values reach Bedrock before publication suppression. | Medium | Adopting organization | Require explicit policy and CLI opt-in; authorize transfer and provider retention before enablement. Each adoption and policy change. |
| Metric definition or source data is wrong although the receipt is valid. | High | Metric author and approver | Data checks, exact SQL, plain-language definition, mapping review queue, human approval. Each report. |
| Suppression policy is wrong for a specific funder or jurisdiction. | High | Adopting organization | CMS-modeled default is labeled; operator chooses authoritative local policy and tests configuration. Each report policy. |
| Manual NVDA/VoiceOver validation is incomplete. | Medium | Maintainer | Complete and sign the dated walkthrough before representing the ACR as complete. Before next release. |
| Dynamic SQL scanner waivers obscure a future unsafe construction. | Medium | Maintainer | Narrow suppressions link issue 52; identifier quoting and trusted-spec boundary reviewed quarterly. |

*Last reviewed: 2026-07-12 · Recheck: quarterly and before each release.*
