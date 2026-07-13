# Accessibility Conformance Report

Product: outcome-receipts generated trace view. Evaluation target: WCAG 2.2 AA
and the web-content clauses of EN 301 549 v3.2.1. VPAT-style status terms are
Supports, Partially Supports, Does Not Support, and Not Applicable.

| Requirement | Status | Evidence |
|---|---|---|
| Text alternatives and non-text content | Supports | Charts carry SVG title/description and an equivalent data table; trace is text. |
| Info and relationships | Partially Supports | Semantic headings, scoped headers, caption, and definition lists are auto-gated; NVDA/VoiceOver table review is pending. |
| Contrast and use of color | Supports | Dark text on white and axe color-contrast gate; meaning does not rely on color. |
| Keyboard and focus | Supports | Native links only; no custom controls, traps, overlays, or sticky content. |
| Reflow and text resize | Supports | Browser gate asserts no horizontal overflow at 320 CSS px; content is linear. |
| Page titled and language identified | Supports | Localized title and valid `html lang` for EN/ES. |
| Name, role, value and status messages | Not Applicable | No forms, custom widgets, live regions, or stateful controls. |

## WCAG 2.2 additions

| Success criterion | Status | Rationale |
|---|---|---|
| 2.4.11 Focus Not Obscured | Supports | No author-created overlay or fixed content. |
| 2.5.7 Dragging Movements | Not Applicable | No drag interaction. |
| 2.5.8 Target Size | Supports | Links are inline-text exceptions; no pointer-only controls. |
| 3.2.6 Consistent Help | Not Applicable | Single offline page with no help mechanism. |
| 3.3.7 Redundant Entry | Not Applicable | No data entry. |
| 3.3.8 Accessible Authentication | Not Applicable | No authentication. |

## Known gap

Manual VoiceOver and NVDA task walkthroughs are not complete. Until both rows in
the dated walkthrough are signed, this ACR reports Partially Supports and must not
be represented as a completed human WCAG conformance assessment.

*Last verified: 2026-07-12 · Recheck: every release and after any HTML change.*
