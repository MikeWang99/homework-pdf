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
  "owners": ["q5"],
  "reviewed": true
}
```

Roles are `stem`, `shared`, and `choice`. `stem/shared` assets are rendered after the question context/stem and before choices. A `choice` asset is rendered directly with the matching choice and **must** have `choice_label`; mismatches are hard errors. Compact legacy `question.assets[]` and `question.asset` are still accepted.

## Math

The canonical bank remains `markdown+latex`. Homework PDF v2 supports inline `$...$` and display `$$...$$` plus the documented common physics command subset implemented in the builder. Unknown LaTeX commands are a hard build error instead of being silently dropped or printed incorrectly.

## Response area

Free-response questions receive **unruled blank space** only. No `Response:` label and no writing lines. Multi-part labels remain part of the question text; the blank area follows the complete question.

## Selection

`--question-ids` and `--ids-file` select exact IDs in the supplied order. Duplicates and unknown IDs are rejected before rendering.
