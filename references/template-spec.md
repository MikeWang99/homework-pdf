# Homework template contract · v2

The deterministic builder uses these stable layout defaults. A user-supplied template is validated as A4 portrait and retained as provenance; v2 does **not** claim to dynamically reverse-engineer arbitrary template typography.

- A4 portrait, `595.276 x 841.890 pt`.
- Left/right content margin: `18 mm`.
- Top content margin: `31 mm`; bottom content margin: `19 mm`.
- Header title: centered Helvetica-like role, ~12 pt, with thin rule.
- Page 1 score row: `Total Points`, `Score`, `Accuracy`; unavailable values remain blank rather than using dash placeholders.
- Question stem: ~11 pt sans-serif role; choices: ~11 pt serif/math role.
- Required stem/shared diagrams stay with the stem through a `KeepTogether` compound block.
- Choice images are rendered next to their matching choices, never collected above all options.
- Free-response questions reserve unruled blank space only.
- Footer: `Mike's Physics - Pocket Cosmos` plus `Page X of Y`.

The source template's example questions/figures are never copied.
