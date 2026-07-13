# Screen-reader and keyboard walkthrough — 2026-07-12

Surface: generated `trace.html`. Primary task: locate a figure, understand its
definition and caveat, and inspect the receipt fields that support it.

## Automated evidence

The generated English and Spanish pages have one `h1`, a unique heading for each
figure, a captioned table with scoped column headers, definition-list receipt
details, visible links, valid document language, and no script. The merge gate
runs axe with WCAG 2.2 AA tags, pa11y, Lighthouse accessibility ≥0.90, 320 CSS px
reflow, and reduced-motion checks. Keyboard operation consists of standard anchor
links; there are no custom controls, focus traps, dragging, forms, authentication,
timeouts, or animation.

## Required assistive-technology pairings

| Pairing | Result | Reviewer evidence |
|---|---|---|
| VoiceOver + Safari on macOS | Not yet executed | A human must record announced headings, caption/header association, link names, and definition-list navigation. |
| NVDA + Firefox or Chrome on Windows | Not yet executed | A human must record the same task and any browse/table mode differences. |
| VoiceOver + Safari on iOS | N/A | The repo emits a local desktop report artifact, not a mobile web/PWA surface. |

The two unexecuted rows are a release review blocker. They are not reported as
passes based on static markup or browser automation.

## Keyboard-only review

Browser-native Tab and Shift-Tab reach each metric link in source order. Enter
moves to the matching figure heading; browser Back returns to the table. Focus is
not obscured because the page has no fixed or sticky content. Escape, arrow-key
widget behavior, and skip links are N/A because there is no modal, composite
widget, or repeated site navigation.

Reviewer: automation and source review by Codex; manual AT sign-off pending.
