# AI impact assessment: optional narrative drafting

## People and decisions affected

Grant and program staff may use the drafted prose in a funder report. Funders may
make funding decisions based on the report, but the model does not compute the
figures or decide eligibility. Clients can be indirectly affected if misleading
framing changes how program performance is understood.

## Inputs and outputs

The model receives a filled narrative plus receipted scalar display allowlist.
Client rows, direct identifiers, SQL, paths, and receipt hashes are excluded. The
output is prose that must pass grounding before suppression, pass grounding again
after redaction, and receive named human approval.

## Benefits and harms

The benefit is editorial assistance without delegating arithmetic. Plausible
nonnumeric misinterpretation, disclosure of a small aggregate before suppression,
and provider-side retention are the main harms. The tool cannot prove source-data
consent, completeness, or fairness.

## Decision and conditions

The feature may remain available only as an opt-in seam. Organizations must
authorize the cloud transfer, select and pin a Bedrock model, review provider
logging/retention, and perform the final qualitative review. A path that lets the
model create a figure or bypass either grounding gate is prohibited.

Owner sign-off: Chelsea Kelly-Reif, 2026-07-12. Reassess on any model, prompt,
provider, data boundary, approval, grounding, or suppression change.
