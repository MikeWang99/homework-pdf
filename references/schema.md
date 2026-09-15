# Input schema and asset resolution

The preferred input is a question-bank JSON file. Paths are relative to the JSON file's directory unless they are absolute.

```json
{
  "collection": {
    "title": "AP Physics 2 - Circuits",
    "course": "AP Physics 2",
    "template_title": "AP Physics 2 - Circuits"
  },
  "assignment": {
    "total_points": null,
    "score": "",
    "accuracy": ""
  },
  "questions": [
    {
      "id": "circuits-2019-q05b",
      "stem_markdown": "A resistance network is shown below.",
      "type": "structured_response",
      "official_marks": 4,
      "knowledge_points": ["Kirchhoff's laws", "equivalent resistance"],
      "assets": [
        {"path": "assets/figures/circuits-2019-q05b.png", "role": "stem", "alt": "Resistance network"}
      ],
      "source": {"document": "2019_section_2.pdf", "pdf_page": 10, "original_id": "5(b)"},
      "answer": {"summary": "...", "mark_points": ["..."]}
    }
  ],
  "assets": [
    {
      "id": "circuits-2019-q05b-figure",
      "file": "assets/figures/circuits-2019-q05b.png",
      "role": "stem",
      "owners": ["circuits-2019-q05b"]
    }
  ]
}
```

## Accepted question text fields

Use the first non-empty field in this order: `stem_markdown`, `stem`, `prompt`, `question`, `text`. Basic Markdown line breaks are supported. If a source bank stores already-rendered HTML/ReportLab markup, normalize or escape it before passing it to the builder; do not allow arbitrary HTML to change the page layout.

## Accepted points fields

Use `points`, then `official_marks`, then `marks`. If none exists, count the question as zero points and leave a warning in the build report. A top-level `assignment.total_points` overrides the computed sum.

## Accepted image forms

The builder resolves images in this order:

1. `question.asset_ids` through the top-level `assets[].id` to `assets[].file`.
2. `question.assets[].path`, `question.assets[].file`, or `question.assets[].asset`.
3. `question.asset` when it is a string.

For a question-level asset list, preserve the listed order. `role: stem`, `choice`, and `shared` are display hints; the builder does not guess ownership or crop images. A missing path is a hard error.

## Answers

For an aligned answer PDF, the builder reads `answer` first and falls back to `solution_markdown` or `explanation`. It accepts answer strings, lists, and dictionaries. Dictionaries are rendered in stable key order with `summary`, `final`, `answer`, `mark_points`, and `parts` preferred before any remaining keys. Student PDFs never render answer data.

## Selection rules

`--question-ids` and `--ids-file` select by exact `id`. Selection order comes from the comma-separated argument or IDs file, not from sorting. Duplicate IDs are rejected. Unknown IDs are rejected before PDF creation.
