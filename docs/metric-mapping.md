# Metric mapping review queue

`receipts map` translates logical funder requirements into candidate SQL over a
schema-variant CSV. It reads the header only. It does not inspect client rows,
execute SQL, edit a report spec, or approve a candidate.

```console
receipts map \
  --data exports/services.csv \
  --requirements requirements.json \
  --out mapping-review.json
```

Requirements are explicit about aggregation semantics; the mapper only resolves
logical fields to source columns:

```json
{
  "requirements": [
    {
      "metric_id": "clients_served",
      "description": "Unduplicated clients served",
      "definition": "Distinct participants in the reporting export.",
      "aggregation": "count_distinct",
      "field": "client_id"
    },
    {
      "metric_id": "permanent_exits",
      "description": "Exits to permanent housing",
      "definition": "Enrollments whose recorded exit destination is permanent.",
      "aggregation": "count_rows",
      "filters": [{"field": "exit_destination", "equals": "Permanent"}]
    }
  ]
}
```

Supported aggregations are `count_rows` and `count_distinct`. Canonical header
matches score 1.0; documented aliases (for example `PersonalID` for `client_id`)
score 0.9. Both remain `review_required` with decision `pending`. A missing or
ambiguous field is `blocked`, carries no `metric_spec`, and makes the command exit
nonzero. The review file is evidence for a human decision, not an executable spec.

This boundary is deliberate: a header match cannot prove that a local field has
the funder's intended population, date window, deduplication rule, or category
semantics. A reviewer must compare the candidate SQL and definition to the local
data dictionary before copying an approved candidate into a report spec.
