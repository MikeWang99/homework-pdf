# v2.2.0 — Canonical math delimiter guard

- Added a pre-render hard gate for bare mathematical syntax outside `$...$` / `$$...$$`
- Rejects forms such as `U_K`, `v_0`, `x^2`, bare `\mu_s`, and unmatched dollar delimiters
- Keeps valid inline/display Markdown+LaTeX behavior unchanged
- Does not globally reinterpret underscores, so ordinary identifiers are not silently reformatted by the renderer
- Error messages direct the caller to fix the canonical physics-bank record rather than blaming fonts
- Layout-block text receives the same math validation as ordinary stems/choices
- Added regression coverage proving `$U_K$` renders without a literal underscore while bare `U_K` fails before PDF generation
