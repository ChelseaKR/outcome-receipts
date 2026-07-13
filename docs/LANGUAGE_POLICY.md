# Language policy

Supported public artifact tags are `en` and `es`. The local CLI accepts an exact
`--locale` value and defaults to `en`; it has no HTTP endpoint, CDN, cookie, user
profile, or `Accept-Language` negotiation. `Content-Language` and `Vary` headers
are therefore N/A.

An unsupported internal call falls back to English so an export does not become
partially localized. The CLI parser rejects unsupported user input before running.
Author-provided report prose and metric definitions are not translated by the
catalog and must already match the selected artifact language.

Adding a regional locale follows BCP 47 fallback from the exact tag to its primary
language, then English, and requires a locale-acceptance artifact before release.

*Last verified: 2026-07-12 · Recheck: every release and locale change.*
