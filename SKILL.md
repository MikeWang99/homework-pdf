---
name: homework-pdf
description: Generate deterministic, validated physics homework PDFs from question-bank v2 records, with correct stem/choice asset placement, explicit math compatibility checks, template validation, and post-build QA.
---

# Homework PDF v2

Use this Skill to turn selected question-bank IDs into a printable student PDF. The bank is the source of truth; do not manually retype or rearrange question content when the builder can consume it directly.

Read `references/schema.md` and `references/template-spec.md` before execution.

## Hard requirements

- Preserve selected wording unless the user explicitly requests adaptation.
- Freeze selection order from explicit IDs; never silently export the entire bank.
- Validate every selected record before rendering: non-empty text, resolvable assets, matching choice-image labels, and supported math commands.
- `stem/shared` figures stay with the stem. `choice` figures render with their matching option via `choice_label`.
- Free-response space is unruled blank space; no response label or writing lines.
- Student numbering is export order (`1.`, `2.`, ...), never source-paper numbering.
- Unknown/unsupported LaTeX is a hard error. Do not silently degrade mathematical notation.
- A supplied template must be A4 portrait; the builder validates this rather than merely checking file existence.

## Standard workflow

1. Inspect selected IDs and the bank's asset manifest.
2. Build with a machine-readable report:

   ```bash
   python "$SKILL_DIR/scripts/build_homework_pdf.py" \
     --manifest /path/to/question-bank/questions.json \
     --question-ids q001,q007,q014 \
     --template /path/to/template.pdf \
     --output /path/to/homework.pdf \
     --report "$TMPDIR/homework-build-report.json"
   ```

3. Run the post-build validator:

   ```bash
   python "$SKILL_DIR/scripts/validate_homework.py" /path/to/homework.pdf \
     --build-report "$TMPDIR/homework-build-report.json" \
     --report "$TMPDIR/homework-validation.json"
   ```

4. Render final PDF pages to images and visually inspect every page, especially large diagrams, circuits/graphs, multi-part questions, choice-image questions, and page breaks. Rebuild after clipping, overlap, wrong option-image association, bad math, missing footer, or missing page number.
5. Deliver only validated final PDF(s).

## Useful options

- `--ids-file FILE`: one question ID per line.
- `--answers-output FILE`: page-aligned teacher/answer copy.
- `--title TEXT`, `--student-name TEXT`, `--show-source`.
- `--front-matter FILE`: explicit user-supplied standalone front page.
- `--question-font-path`, `--option-font-path`; `--font` remains a legacy alias for the question font.

## Boundaries

This Skill renders existing bank records. It does not scrape new exam papers, infer official answers, or mutate the source bank. If the bank itself is incomplete, fix it with `physics-bank` first instead of patching the omission inside the PDF renderer.
