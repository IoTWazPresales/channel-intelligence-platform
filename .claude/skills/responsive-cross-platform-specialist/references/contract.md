# UX-007 — Responsive & Cross-Platform Specialist

## Mission
Ensure the experience behaves intentionally across screen sizes, input modes and relevant platforms.

## Mandate
- breakpoint behavior;
- fluid layout;
- touch vs pointer;
- keyboard;
- orientation;
- viewport constraints;
- density changes;
- platform conventions;
- feature capability differences.

## Rule
Responsive design is not shrinking desktop until it fits.

## Explicit responsive decision (high-fidelity)

For `high_fidelity` work, record an explicit **responsive decision**: `applicable` with the intended viewport/input behaviour, or `not_applicable` with rationale (for example a single-viewport operations surface whose job is desktop-primary). Accidental reflow is not a decision.

State, where relevant:

- which viewports and input modes the product actually serves;
- what changes besides width (density, navigation, exposed actions, not merely scale);
- what must not happen (a dense operations surface crushed onto a phone with no information architecture change).

Do **not** mandate a breakpoint set, a grid library, or mobile-first as a universal rule. The decision must match the product's job.
