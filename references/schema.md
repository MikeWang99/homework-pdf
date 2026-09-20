# Input schema and asset resolution · v2

The preferred input is the `physics-bank` v2 schema. Paths are relative to the question JSON directory unless absolute.

## Question text

Use the first non-empty field: `stem_markdown`, `stem`, `prompt`, `question`, `text`. `context` is rendered before the stem when present. Structured subquestions come from `subquestions`, `question_parts`, or `parts`; text heuristics are only a compatibility fallback.

## Points

Use `points`, then `official_marks`, then `marks`. If none exists, the computed total omits that question rather than inventing marks. A top-level `assignment.total_points` overrides the computed total.

## Assets

Canonical v2 assets are top-level records referenced by `question.asset_ids`:

```json
{
  "id": "q5-choice-a",
  "file": "assets/figures/q5-choice-a.png",
  "role": "choice",
  "choice_label": "A",
  "source_width_pt": 217.5,
  "source_height_pt": 125.25,
  "owners": ["q5"],
  "reviewed": true
}
```

Roles are `stem`, `shared`, and `choice`. `stem/shared` assets are rendered after the question context/stem and before choices. A `choice` asset is rendered directly with the matching choice and **must** have `choice_label`; mismatches are hard errors. Compact legacy `question.assets[]` and `question.asset` are still accepted.

When an image was cropped from a source PDF, `source_width_pt` and `source_height_pt` should record the image's original displayed width and height in PDF points. When both are present, the renderer uses these physical dimensions instead of interpreting PNG/JPG pixels as PDF points. This preserves the source PDF's visual scale and is especially important for choice diagrams.

## Ordered figure/text layout

`question.asset_ids` identifies which assets belong to the question; it does not encode where an asset belongs in the question narrative. For FRQs with figures interleaved with prose, use the optional ordered `layout_blocks` field:

```json
[
  {"text": "A sample of gas is shown below."},
  {"asset_id": "q46-pv-initial", "max_height_mm": 70},
  {"text": "A student draws a correct bar chart."},
  {"spacer_lines": 1}
]
```

The builder accepts the explicit equivalent spellings `{"type":"text", ...}`, `{"type":"figure", ...}`, and `{"type":"response_space", "lines": 1}`. The compact forms above are preferred for hand-authored derived manifests.

- Text blocks render in declared order; export numbering is prefixed only to the first text block.
- Figure blocks reference `stem`/`shared` assets exactly once. Every `stem`/`shared` asset listed in `asset_ids` must be placed in the layout blocks.
- `max_height_mm` is a local display cap. When source dimensions are present, `source_width_pt`/`source_height_pt` still control the figure's physical source scale within that cap.
- `spacer_lines`/`response_space` creates unruled answer space; it does not draw writing lines.
- If `layout_blocks` is absent, `stem`/`shared` assets retain the legacy placement after the stem.

## Math

The canonical bank remains `markdown+latex`. Homework PDF v2 supports inline `$...$` and display `$$...$$` plus the documented common physics command subset implemented in the builder. Unknown LaTeX commands are a hard build error instead of being silently dropped or printed incorrectly.

## Response area

Free-response questions receive **unruled blank space** only. No `Response:` label and no writing lines. Multi-part labels remain part of the question text. The default builder inserts one extra blank line after each structured FRQ subquestion; use ordered `layout_blocks` with `spacer_lines`/`response_space` when the response space must be placed between prose and figures.

## Selection

`--question-ids` and `--ids-file` select exact IDs in the supplied order. Duplicates and unknown IDs are rejected before rendering.
