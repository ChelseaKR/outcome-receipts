# Every number has a receipt: six-week discovery campaign

## Objective and audience

The primary objective is to record 10 completed demo runs and three serious
schema-mapping conversations within six weeks of the first beta release. Stars
are a secondary signal, not the activation event.

The primary audience is grant, program, evaluation, data, and operations staff
at small-to-mid-sized human-services nonprofits. The secondary audience is
nonprofit-technology, civic-technology, and responsible-AI practitioners who can
evaluate or extend the implementation.

The project should be introduced as a reviewable reporting trust chain. It
should not be described as a compliance product, a replacement for domain
review, or the inventor of receipt-based verification.

## Message hierarchy

1. Manual copying and generated prose can separate a reported figure from its evidence.
2. Every figure should be computed deterministically and carry a receipt.
3. An unbound number or uncertain mapping must block or route to a human.
4. Run the synthetic demo and report where the trust chain becomes unclear.

Proof comes from the runnable demo, committed tests and evaluation, readable
trace view, suppression behavior, and independent verification command.

## Channel priorities

| Priority | Channel | Purpose | Effort |
| --- | --- | --- | --- |
| 1 | Direct practitioner invitations | Obtain detailed feedback and real mapping questions. | Medium |
| 1 | NTEN and TechSoup communities | Reach nonprofit staff already discussing technology practice. | Medium |
| 1 | GitHub release, topics, Discussions, and issues | Convert interest into a runnable trial or contribution. | Low |
| 2 | NHSDC conference or community | Reach HMIS and human-services data specialists. | Medium |
| 2 | LinkedIn | Let practitioners and responsible-AI peers share the demonstration. | Low |
| 3 | Broad launch sites | Revisit only after practitioner proof exists. | High |

No paid distribution is planned. Time should go to direct feedback and reusable
technical material before broad reach.

## Calendar

| Week | Content or action | Channel | Dependency | Status |
| --- | --- | --- | --- | --- |
| 1 | Publish the beta release and five-minute demo | GitHub | Signed release tag and PyPI publisher | Prepared |
| 1 | Add social preview, Discussions, and structured issue forms | GitHub | Merge discovery assets | Prepared |
| 2 | Send 10 direct practitioner invitations | Email or direct message | Beta release URL | Ready to send |
| 2 | Publish the canonical explainer | Owned profile or blog | Beta release URL | Drafted |
| 3 | Share the practitioner discussion prompt | NTEN and TechSoup | Two completed demo runs | Drafted |
| 4 | Submit the human-services session abstract | NHSDC | One mapping conversation | Drafted |
| 4 | Publish a technical grounding-gate walkthrough | GitHub or engineering community | Feedback from early trials | Planned |
| 5 | Publish an anonymized mapping walkthrough | Owned and community channels | Design-partner permission | Planned |
| 6 | Review sources, activations, and objections | Repository traffic and issues | Six weeks of observations | Planned |

Keep roughly one fifth of the calendar open for questions or community events
that arise during the campaign.

## Assets

Must-have assets are the five-minute demo, social card, canonical explainer,
direct invitation, two community drafts, session abstract, demo-run issue form,
and schema-mapping issue form. A narrated video is useful after the command flow
has been tested by people who did not build it.

## Measures

| Measure | Six-week target | Source |
| --- | ---: | --- |
| Confirmed completed demo runs | 10 | Demo-run issues and direct replies |
| Serious mapping conversations | 3 | Schema-mapping issues or private notes |
| Practitioner interviews | 5 | Maintainer log |
| External mentions or backlinks | 3 | GitHub referrers and manual search |
| Meaningful outside issues or contributions | 2 | GitHub |
| Qualified repository stars | 25 | GitHub |
| Accepted article, webinar, or session | 1 | Publisher or event response |

Run `scripts/repo-traffic.sh` each Friday and append the JSON output to a private
campaign log. GitHub traffic is a rolling 14-day view, so it should not be the
only historical record.

## Risks and responses

- **Interest without activation.** Keep the main call to action on the demo, not
  the star button, and follow up on blocked runs.
- **Privacy mistakes in public feedback.** Repeat that issues must not contain
  client rows, identifiers, credentials, or real exports. Provide an anonymized
  column-inventory path.
- **Overclaiming the tool.** Use the prepared copy, state that policy selection
  remains the operator's responsibility, and describe prior verification work
  honestly.
- **A broad developer audience overwhelms practitioner signal.** Start with
  direct outreach and domain communities before broad launch sites.
