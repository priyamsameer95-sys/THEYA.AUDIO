---
name: web-design-guidelines
description: Review and audit existing web applications against Vercel's Web Interface Guidelines. Catches visual hierarchy flaws, spacing drift, broken tap targets, and accessibility pitfalls.
---

# Web Design Guidelines: Interface Audit Checklist

Based on Vercel's Web Interface Guidelines. Use this checklist at the end of every frontend feature to audit code for polish and usability.

## 1. Visual Hierarchy & Spatial Consistency
- [ ] **Spacing Scale:** Are all paddings, margins, and gaps conforming to a strict 4px/8px scale (`4px`, `8px`, `12px`, `16px`, `24px`, `32px`)?
- [ ] **Contrast Hierarchy:** Is there a clear primary focal point on the screen, followed by secondary actions and muted metadata?
- [ ] **Border & Line Discipline:** Are dividers and borders subtle (`1px solid rgba(0,0,0,0.06)` or `--border-subtle`) rather than heavy and distracting?

## 2. Interactive States & Touch Targets
- [ ] **Minimum Touch Targets:** Are all clickable buttons, links, and icons at least `44x44px` on mobile/touch interfaces?
- [ ] **Interactive States:** Does every clickable element provide distinct `:hover`, `:active`, and `:focus-visible` styles?
- [ ] **Focus Rings:** Is the default browser focus ring replaced with an intentional, high-contrast focus indicator for keyboard navigators (`:focus-visible`)?

## 3. Loading, Empty & Error States
- [ ] **No Blank Screens:** Does every async view render an initial skeleton or subtle loading indicator?
- [ ] **Helpful Empty States:** When a list or search result is empty, does it explain why and suggest an action?
- [ ] **Non-destructive Error Handling:** If an error occurs, is user input preserved so they don't have to retype everything?

## 4. Accessibility (A11y)
- [ ] **Semantic Markup:** Use native `<button>`, `<nav>`, `<main>`, `<header>`, `<footer>` instead of clickable `<div>`s.
- [ ] **Screen Reader Labels:** Do icon-only buttons include an `aria-label` or visually hidden text?
