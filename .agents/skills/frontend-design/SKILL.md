---
name: frontend-design
description: Creative and distinctive visual design guidelines for web UIs. Steers away from cookie-cutter AI aesthetic (Inter font, generic purple gradients) toward intentional, bespoke interfaces.
---

# Frontend Design: Beyond the AI Aesthetic

Most AI-generated interfaces default to the exact same statistical center: generic Inter font, purple/indigo gradients, floating white cards with subtle box-shadows, and cookie-cutter grid layouts. This skill guides the creation of distinctive, memorable, and context-appropriate interfaces.

## 1. Intentional Typography
- **Match Font to Domain:**
  - *Editorial & Long-form:* Rich serifs (e.g., Newsreader, Merriweather, Georgia, Playfair).
  - *Developer & Technical Tools:* Clean geometric or humanistic sans (e.g., Geist, IBM Plex Sans, Inter) paired with distinctive monospaces (JetBrains Mono, Fira Code).
  - *Luxury & High-touch:* Elegant high-contrast display fonts.
- **Typographic Scale:** Establish a consistent modular scale (e.g., 1.25x or 1.33x) with explicit `letter-spacing` tightening on large headings and relaxed `line-height` on body prose.

## 2. Cohesive & Purposeful Color Palettes
- **Avoid Cliché Gradients:** Drop the generic indigo-to-purple gradient.
- **Dominant + Accent Harmony:** Anchor the UI around a confident, restrained neutral base (warm slate, bone, or deep obsidian) and introduce one intentional, high-contrast accent.
- **Semantic Contrast:** Ensure text meets WCAG AA contrast ratios (4.5:1 for normal text, 3:1 for large text).

## 3. Spatial Rhythm & Micro-Interactions
- **Consistent Grid Rhythm:** Use a 4px / 8px spatial grid for all margins, padding, and gaps.
- **Physical Feedback:** Hover, focus, and active states should feel tactile and responsive with crisp transitions (150ms–200ms ease).
- **Surface Elevation:** Use subtle borders (`1px solid rgba(0,0,0,0.06)`) and ambient occlusion rather than heavy blurred drop shadows.
