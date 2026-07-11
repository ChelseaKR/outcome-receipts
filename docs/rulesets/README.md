# Branch rulesets (exported artifacts)

`main.json` is the ruleset of record for the `main` branch (CICD-12): PRs
required, the three `ci.yml` checks (`verify`, `security`, `accessibility`)
required and up to date, stale reviews dismissed on push, review threads
resolved, force-pushes and deletions blocked, linear history, signed commits,
and **no bypass actors** (admins included).

`required_approving_review_count` is `0` deliberately: this is a
single-maintainer repository and GitHub does not count self-approval, so a
count of 1 would deadlock every merge. Raise it to 1 the day a second
maintainer exists.

Applying it is a live-settings change, so it is owner-only (⛔USER):

```sh
gh api -X POST repos/ChelseaKR/outcome-receipts/rulesets \
  --input docs/rulesets/main.json
```

Note: branch rulesets on a **private** repo require a paid plan; on a public
repo they are free. This file is committed either way so the intended
protection is reviewable and diffable. After the ruleset is live, restore the
"main is protected" language in CONTRIBUTING.md (remediation P0-1 step 4). If
the live ruleset is ever edited in the UI, re-export it here
(`gh api repos/ChelseaKR/outcome-receipts/rulesets/<id>`) so the file stays
the source of truth.
