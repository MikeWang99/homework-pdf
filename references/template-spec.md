# HomeWork-Template measured layout

These defaults were measured from the supplied `/Users/mikewang/Desktop/物理习题题库汇总/HomeWork-Template.pdf` and are intentionally expressed as code-level constants so repeated exports are stable.

- Media box: A4 portrait, `595.276 x 841.890 pt`.
- Left/right content margin: approximately `18 mm`.
- Top content margin below the header fields: approximately `31 mm`.
- Bottom content margin above the footer rule: approximately `19 mm`.
- Header title: centered, black sans-serif, approximately `12 pt`.
- Header rule: black, approximately `0.5 pt`, from `18 mm` to `18 mm` side margins, about `18 mm` below the top edge.
- Score row: on page 1 only, right aligned below the rule, approximately `8.5-9 pt`, with the literal fields `Total Points`, `Score`, and `Accuracy`; later pages leave this row empty.
- Main question number: left aligned, approximately `16 pt` black sans-serif.
- Question stem: a clean sans-serif-like role, approximately `11 pt` with stable leading; this is the default role for question text and metadata.
- Multiple-choice options: a separate serif/math-like role, approximately `11 pt` with stable leading, visually matching the formula-heavy option lines in the supplied reference.
- Multiple-choice image layout: when a selected question has an image, place it directly below the stem and center it within the content column before rendering the options.
- Footer rule: black, approximately `0.5 pt`, about `14 mm` above the bottom edge.
- Footer note: centered at approximately `8.5 mm` above the bottom edge, exactly `Mike's Physics - Pocket Cosmos`.
- Added page number: right aligned on the same footer baseline as `Page X of Y`.

The template's example PV diagrams and example question text are not reusable content. Only the layout, fields, spacing, and footer treatment are inherited.

The screenshot supplied with the skill request is a visual style reference only. Its source question, answer markings, and handwritten annotations are never copied into generated homework.
