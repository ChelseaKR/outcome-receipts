# Branch rulesets (exported artifacts)

`main.json` is the ruleset of record for the `main` branch (CICD-12): PRs
required, the three `ci.yml` checks (`verify`, `security`, `accessibility`)
required and up to date, stale reviews dismissed on push, review threads
resolved, force-pushes and deletions blocked, linear history, signed commits,
and **exactly one bypass actor, the repository owner** (`RepositoryRole` 5,
`bypass_mode: always`) — deliberately and permanently. Read "Why the owner can
bypass" below before touching that field.

`required_approving_review_count` is `0` deliberately: this is a
single-maintainer repository and GitHub does not count self-approval, so a
count of 1 would deadlock every merge. Raise it to 1 the day a second
maintainer exists.

## Two committed files, and which one describes the repository

There are two ruleset definitions in this repository and they are not copies of
each other:

| File | `name` | `ref_name.include` | Required contexts |
|---|---|---|---|
| `.github/rulesets/main.json` | `protect-main` | `refs/heads/main` | six |
| `docs/rulesets/main.json` (this one) | `main` | `~DEFAULT_BRANCH` | three |

The commit record explains the split. This file landed first, on 2026-07-11
(#39), and the CHANGELOG entry that added it calls it "the intended full branch
ruleset for `main`", whose "pull-request, review, linear-history, and
signed-commit rules remain recorded here for a future multi-maintainer policy
update" — written when the live ruleset enforced less than the file did.
`.github/rulesets/main.json` landed two days later, on 2026-07-13 (#54), named
after the ruleset that had by then actually been applied and listing the six
contexts it really requires. This file was never retired, and neither file
mentions the other.

**`.github/rulesets/main.json` is the one that matches the live ruleset**
(id `18752852`, `protect-main`, `enforcement: active`). Read it to learn what
protects `main` today. This file stays committed because it is what the CICD-12
remediation reviewed and because the rules it carries beyond the live set
record an intent that has not been withdrawn — but it is an intent, not a
description.

Both files now record the owner's bypass, because a file that omits it is a
lockout waiting for whoever applies it, whichever of the two they reach for.

## Why the owner can bypass

`bypass_actors` holds exactly the repository owner's standing bypass
(`RepositoryRole` 5, `bypass_mode: always`), deliberately and permanently: an
agent once applied a ruleset with no bypass and locked the owner out of their
own repository, and restoring access took a sweep across eighteen
repositories. An empty list here is not a stricter gate, it is the lockout.

This page used to say the opposite — "**no bypass actors** (admins included)" —
while both JSON files said `"bypass_actors": []` and the live ruleset carried
the owner's bypass, so the documented posture and the enforced one disagreed
with nothing in the repository comparing them. The old argument is not wrong
about the risk it names, an admin merging past a red check; it is wrong about
which risk is larger, and the larger one has already happened. Everything else
on this page still addresses the smaller one: a pull request is required, the
required checks are required, the branch must be up to date, and history cannot
be rewritten. The bypass is the way back in when a required check is wedged,
not a routine merge path.

Two things keep it that way, and they are deliberately not one thing:

- `scripts/check_ruleset.py` holds the live ruleset and each committed file
  **independently** against that one actor, rather than only comparing them to
  each other. Comparing them would report conformance on the day both were
  emptied together, which is the incident recurring with a green tick on it.
- `tests/test_ruleset.py` runs that logic offline against the committed files
  and a recorded live payload, and pins all three failure directions: a second
  actor granted a bypass, the owner's bypass gone from the live ruleset, and
  both sides emptied at once (two findings, never zero).

If you are reading this because the empty list looks more secure and you are
about to restore it: reapplying a ruleset file that omits the owner's bypass is
how the lockout happens. Do not.

## Applying it

Applying it is a live-settings change, so it is owner-only (⛔USER):

```sh
gh api -X POST repos/ChelseaKR/outcome-receipts/rulesets \
  --input docs/rulesets/main.json
```

> **Check `bypass_actors` in the file before running that.** The ruleset this
> creates enforces exactly what the file says, so a file carrying
> `"bypass_actors": []` produces an active ruleset on the default branch that
> the owner cannot bypass. Until 2026-08-28 both committed files said exactly
> that while the live ruleset carried the owner's standing bypass, so following
> this instruction as written would have applied the lockout described above,
> by following this repository's own documented procedure. Note also that
> `POST` *adds* a ruleset rather than replacing `protect-main`: the new one
> would sit alongside it and both would be enforced.
> `.venv/bin/python scripts/check_ruleset.py` fails when either committed file
> omits the owner's bypass. Run it first.

Note: branch rulesets on a **private** repo require a paid plan; on a public
repo they are free. This file is committed either way so the intended
protection is reviewable and diffable. After the ruleset is live, restore the
"main is protected" language in CONTRIBUTING.md (remediation P0-1 step 4). If
the live ruleset is ever edited in the UI, re-export it here
(`gh api repos/ChelseaKR/outcome-receipts/rulesets/<id>`) so the file stays
the source of truth.

## Checking it

```sh
.venv/bin/python scripts/check_ruleset.py                    # committed files only
gh api repos/ChelseaKR/outcome-receipts/rulesets/18752852 |
  .venv/bin/python scripts/check_ruleset.py --live -         # and the live ruleset
```

The script never reaches the network itself: the caller hands it the live JSON,
so the thing that fetches and the thing that judges stay separable. It exits
`0` when the owner's bypass is recorded in both committed files, and enforced
live if a live payload was supplied, and nothing else can bypass on either
side; `1` otherwise, naming every finding.

Reading `bypass_actors` needs a token with permission to read repository
administration. A token without it gets a reduced payload that omits the field
entirely, and the script reports that it could not read the field rather than
reading the omission as "no one bypasses".
