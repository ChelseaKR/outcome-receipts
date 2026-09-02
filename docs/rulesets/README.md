# Branch rulesets (exported artifacts)

The ruleset of record for `main` (CICD-12) is
[`.github/rulesets/main.json`](../../.github/rulesets/main.json). It is the export of the
ruleset GitHub is actually enforcing, and it is the only committed ruleset file in this
repository. This directory keeps the reasoning; it no longer keeps a second copy of the
ruleset.

## What is applied, measured rather than intended

Read on **2026-08-29** from `GET /repos/ChelseaKR/outcome-receipts/rulesets/18752852`:

| Field | Value |
|---|---|
| `name` | `protect-main` |
| `enforcement` | `active` |
| `conditions.ref_name.include` | `["refs/heads/main"]` |
| `updated_at` | `2026-08-26T21:27:51.877-07:00` |
| `bypass_actors` | `[{ "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" }]` |
| `current_user_can_bypass` | `"always"` |

Rules: `deletion`, `non_fast_forward`, `required_linear_history`, `required_signatures`,
`pull_request` (0 approvals, stale reviews dismissed, threads resolved, `squash` and
`rebase`), and `required_status_checks` (strict) over six contexts:

`verify` · `security (pip-audit · osv-scanner · gitleaks · zizmor)` ·
`accessibility (pa11y, WCAG2AA, trace.html)` · `dogfood-action` ·
`codeql (python · actions)` · `portfolio standards conformance`

`.github/rulesets/main.json` mirrors all of that.

## Two things this file used to say that were wrong

**"No bypass actors (admins included)."** That was the doctrine, and it is reversed here
rather than quietly dropped, because the reasoning is what needs correcting and not just
the sentence. An empty `bypass_actors` is not a stricter gate. It is a lockout. This
profile requires a pull request, six contexts, a strict up-to-date policy, signed commits
and linear history; with no bypass actor, one wedged check leaves the sole maintainer
unable to merge, unable to push, and unable to delete the ruleset that is blocking them.
An agent applied a no-bypass ruleset elsewhere in this portfolio and restoring access took
a sweep across eighteen repositories. The live ruleset carries the owner's standing
bypass, and the committed file now carries it too:

```json
{ "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" }
```

`RepositoryRole` 5 is admin. `bypass_mode: "always"` and not `"pull_request"`, because a
bypass that only works inside a pull request is no use when the thing that is wedged is
the pull request. One actor, and a repository role rather than a team or a GitHub App: a
second entry in this list would be a real finding, and this one is not.

**"The three `ci.yml` checks."** The live ruleset requires six contexts, not three. That
sentence described `docs/rulesets/main.json`, a second committed ruleset that was removed
in the same change as this rewrite. It was the older of the two files (#39; the `.github`
export arrived with #54), it had drifted away from the live ruleset in four ways at once
(a different `name`, `~DEFAULT_BRANCH` instead of `refs/heads/main`, `merge` among the
allowed merge methods, and three required contexts instead of six), and the apply command
below still pointed at it. Two committed rulesets that disagree with each other and with
the server are two chances to apply the wrong one, so there is now one.

## Applying it is owner-only (⛔USER)

`POST` **adds** a ruleset rather than replacing one, and a ruleset already exists on this
repository. Rules from every applicable ruleset combine while bypass actors are
per-ruleset, so posting this file without first deleting id `18752852` would leave two
rulesets over `main`, and the stricter combination with the narrower bypass wins. Do not
re-apply unless the existing one is going away.

If it ever does need re-applying:

```sh
gh api -X POST repos/ChelseaKR/outcome-receipts/rulesets \
  --input .github/rulesets/main.json
```

Then confirm the bypass survived, because an apply that lands every rule and loses that
actor returns 201 like any other:

```sh
gh api repos/ChelseaKR/outcome-receipts/rulesets/<id> --jq .current_user_can_bypass
```

must read `"always"`.

`required_approving_review_count` is `0` deliberately: this is a single-maintainer
repository and GitHub does not count self-approval, so a count of 1 would deadlock every
merge. Raise it to 1 the day a second maintainer exists.

If the live ruleset is ever edited in the UI, re-export it to
`.github/rulesets/main.json` (`gh api repos/ChelseaKR/outcome-receipts/rulesets/18752852`)
so the file stays the source of truth, and check the bypass list survived the round trip.

## What guards this

`tests/test_ruleset_lockout.py` fails the build if any committed ruleset file would lock
the owner out when applied: an empty `bypass_actors`, an absent key, a non-list, a foreign
actor, or the owner with `bypass_mode: "pull_request"`. It discovers ruleset files by
glob rather than by a hardcoded path, so a second committed ruleset cannot reappear
uncovered the way `docs/rulesets/main.json` did, and it fails if it finds none at all. It
parses rather than greps, because a truncated JSON file still contains the string
`bypass_actors`.

What it does not check is whether the committed export still matches the live ruleset.
That needs a network call, and the gates here do not make one.
