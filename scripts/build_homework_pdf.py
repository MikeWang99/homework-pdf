#!/usr/bin/env python3
"""Build a stable student homework PDF from selected question-bank records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PAGE_W, PAGE_H = A4
MARGIN_X = 18 * mm
TOP_MARGIN = 31 * mm
BOTTOM_MARGIN = 19 * mm
FOOTER_Y = 8.5 * mm
DEFAULT_FOOTER = "Mike's Physics - Pocket Cosmos"


def first_value(mapping: dict, keys: list[str], default=""):
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return default


def question_text(question: dict) -> str:
    value = first_value(question, ["stem_markdown", "stem", "prompt", "question", "text"])
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def points_for(question: dict) -> float:
    value = first_value(question, ["points", "official_marks", "marks"], 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def paragraph_markup(value) -> str:
    """Escape content and allow only a small, deterministic Markdown subset."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = escape(text)
    text = re.sub(r"\$([^$]+)\$", lambda match: f"<i>{format_inline_math(match.group(1))}</i>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    text = text.replace("\n", "<br/>")
    return text


def format_inline_math(text: str) -> str:
    """Make common lightweight LaTeX notation readable without a runtime renderer."""
    replacements = {
        r"\propto": "∝",
        r"\times": "×",
        r"\cdot": "·",
        r"\Omega": "Ω",
        r"\Delta": "Δ",
        r"\theta": "θ",
        r"\pi": "π",
        r"\le": "≤",
        r"\ge": "≥",
        r"\pm": "±",
        r"\,": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\^\{([^{}]+)\}", r"<super>\1</super>", text)
    text = re.sub(r"\^([0-9+-]+)", r"<super>\1</super>", text)
    text = text.replace(r"\sqrt", "√")
    return text


def answer_text(answer) -> str:
    if answer is None:
        return ""
    if isinstance(answer, str):
        return answer
    if isinstance(answer, list):
        return "\n".join(f"- {item}" for item in answer)
    if isinstance(answer, dict):
        preferred = ["summary", "final", "answer", "mark_points", "parts", "explanation"]
        keys = [key for key in preferred if key in answer]
        keys += sorted(key for key in answer if key not in keys)
        chunks = []
        for key in keys:
            value = answer[key]
            if isinstance(value, list):
                value = "\n".join(f"- {item}" for item in value)
            elif isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            chunks.append(f"{key}: {value}")
        return "\n".join(chunks)
    return str(answer)


def load_bank(path: Path) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise ValueError("The manifest must contain a top-level questions array")
    question_index = {}
    for question in questions:
        qid = question.get("id")
        if not qid or qid in question_index:
            raise ValueError(f"Every question needs a unique id; duplicate/missing id: {qid!r}")
        question_index[qid] = question

    asset_records = list(data.get("assets", []))
    for candidate in (path.parent / "asset_manifest.json", path.parent / "manifests" / "asset_manifest.json"):
        if not asset_records and candidate.exists():
            external = json.loads(candidate.read_text(encoding="utf-8"))
            asset_records = external.get("assets", [])
            break
    asset_index = {item.get("id"): item for item in asset_records if item.get("id")}
    return data, question_index, asset_index


def resolve_images(question: dict, bank_root: Path, asset_index: dict[str, dict]) -> list[tuple[Path, str]]:
    refs: list[tuple[str, str]] = []
    for asset_id in question.get("asset_ids", []) or []:
        record = asset_index.get(asset_id)
        if not record:
            raise FileNotFoundError(f"Asset id {asset_id!r} is not present in the asset manifest")
        refs.append((record.get("file") or record.get("path"), record.get("alt") or record.get("caption") or ""))

    if not refs:
        assets = question.get("assets", []) or []
        if isinstance(assets, dict):
            assets = [assets]
        for asset in assets:
            if isinstance(asset, str):
                refs.append((asset, ""))
            else:
                refs.append((asset.get("path") or asset.get("file") or asset.get("asset"), asset.get("alt") or asset.get("caption") or ""))

    if not refs and isinstance(question.get("asset"), str):
        refs.append((question["asset"], ""))

    resolved = []
    for raw_path, caption in refs:
        if not raw_path:
            raise FileNotFoundError(f"Question {question.get('id')} has an empty image reference")
        image_path = Path(raw_path)
        if not image_path.is_absolute():
            image_path = bank_root / image_path
        if not image_path.exists():
            raise FileNotFoundError(f"Image for {question.get('id')} not found: {image_path}")
        if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".bmp"}:
            raise ValueError(f"Unsupported image format {image_path.suffix!r}; rasterize it to PNG/JPG first")
        resolved.append((image_path, caption))
    return resolved


class NumberedCanvasMixin:
    """Two-pass page numbering without changing the body layout."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(page_count)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#222222"))
        self.drawRightString(PAGE_W - MARGIN_X, FOOTER_Y, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


from reportlab.pdfgen.canvas import Canvas


class NumberedCanvas(NumberedCanvasMixin, Canvas):
    pass


def draw_header_footer(canvas, doc, title: str, total: str, score: str, accuracy: str, student: str):
    canvas.saveState()
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica", 12)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 14 * mm, title)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_X, PAGE_H - 18 * mm, PAGE_W - MARGIN_X, PAGE_H - 18 * mm)
    if canvas.getPageNumber() == 1:
        canvas.setFont("Helvetica", 8.7)
        canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 26 * mm, f"Total Points: {total}    Score: {score}    Accuracy: {accuracy} %")
    if student:
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(MARGIN_X, PAGE_H - 26 * mm, f"Student: {student}")
    canvas.line(MARGIN_X, 14 * mm, PAGE_W - MARGIN_X, 14 * mm)
    canvas.setFont("Helvetica", 8.5)
    canvas.drawCentredString(PAGE_W / 2, FOOTER_Y, DEFAULT_FOOTER)
    canvas.restoreState()


def register_local_font(font_path: str | None, registered_name: str) -> str | None:
    if not font_path:
        return None
    font_file = Path(font_path)
    if not font_file.exists():
        raise FileNotFoundError(f"Font not found: {font_file}")
    pdfmetrics.registerFont(TTFont(registered_name, str(font_file)))
    return registered_name


def build_pdf(
    output: Path,
    data: dict,
    selected: list[dict],
    bank_root: Path,
    asset_index: dict[str, dict],
    title: str,
    student: str,
    show_source: bool,
    show_answers: bool,
    question_font_path: str | None,
    option_font_path: str | None,
):
    # The screenshot/template uses two visual text roles: a clean sans-serif
    # question stem and a serif/math-like option line. Keep both deterministic
    # and independently overrideable for banks with a known source font.
    question_font = register_local_font(question_font_path, "LocalHomeworkQuestionFont")
    option_font = register_local_font(option_font_path, "LocalHomeworkOptionFont")
    if question_font is None:
        system_font = Path("/System/Library/Fonts/STHeiti Medium.ttc")
        if system_font.exists():
            pdfmetrics.registerFont(TTFont("LocalHomeworkQuestionFont", str(system_font)))
            question_font = "LocalHomeworkQuestionFont"
        else:
            question_font = "Helvetica"
    if option_font is None:
        option_font = "Times-Roman"

    assignment = data.get("assignment", {}) if isinstance(data.get("assignment", {}), dict) else {}
    total_raw = assignment.get("total_points")
    total = format_number(sum(points_for(q) for q in selected)) if total_raw in (None, "") else str(total_raw)
    score = str(assignment.get("score", ""))
    accuracy = str(assignment.get("accuracy", ""))

    doc = BaseDocTemplate(str(output), pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="homework", frames=frame, onPage=lambda c, d: draw_header_footer(c, d, title, total, score, accuracy, student))])

    styles = getSampleStyleSheet()
    qstyle = ParagraphStyle("question", parent=styles["BodyText"], fontName=question_font, fontSize=11, leading=15, textColor=colors.black, spaceAfter=3 * mm)
    option_style = ParagraphStyle("option", parent=styles["BodyText"], fontName=option_font, fontSize=11, leading=15, textColor=colors.black, spaceAfter=1.5 * mm)
    title_style = ParagraphStyle("question_title", parent=qstyle, fontSize=16, leading=20, textColor=colors.HexColor("#12344D"), spaceAfter=2 * mm)
    source_style = ParagraphStyle("source", parent=qstyle, fontSize=8.2, leading=11, textColor=colors.HexColor("#476477"), spaceAfter=2 * mm)
    caption_style = ParagraphStyle("caption", parent=qstyle, fontSize=8, leading=10, textColor=colors.HexColor("#476477"), alignment=TA_LEFT)
    answer_style = ParagraphStyle("answer", parent=qstyle, fontSize=9.5, leading=13, textColor=colors.HexColor("#12344D"), backColor=colors.HexColor("#F3F7F9"), borderColor=colors.HexColor("#B7C8D2"), borderWidth=.5, borderPadding=7)
    small_style = ParagraphStyle("small", parent=qstyle, fontSize=8.5, leading=11)

    story = []
    for index, question in enumerate(selected, start=1):
        source = question.get("source", {}) if isinstance(question.get("source", {}), dict) else {}
        original = first_value(source, ["original_id", "original_number"], question.get("source_question_number", ""))
        qtitle = question.get("title") or question.get("topic") or (f"Question {original}" if original else "Selected question")
        story.append(Paragraph(f"{index}.", ParagraphStyle("number", parent=title_style, fontName=question_font, fontSize=16, leading=19, spaceAfter=1 * mm)))
        story.append(Paragraph(paragraph_markup(str(qtitle)), title_style))
        if show_source and source:
            source_doc = first_value(source, ["document", "file"], "")
            source_page = first_value(source, ["pdf_page", "source_page", "page"], "")
            source_line = " · ".join(item for item in [str(source_doc) if source_doc else "", f"page {source_page}" if source_page else ""] if item)
            if source_line:
                story.append(Paragraph(paragraph_markup(source_line), source_style))
        stem = question_text(question)
        if stem:
            story.append(Paragraph(paragraph_markup(stem), qstyle))

        # For MCQs with figures, the visual hierarchy is deliberately fixed:
        # stem -> centered figure(s) -> options. This keeps a diagram attached
        # to the question it explains and matches the supplied reference page.
        image_refs = resolve_images(question, bank_root, asset_index)
        image_cap = 150 * mm if len(image_refs) <= 1 else 88 * mm
        for image_path, caption in image_refs:
            image = RLImage(str(image_path))
            max_width = doc.width * 0.96
            max_height = image_cap
            scale = min(max_width / image.imageWidth, max_height / image.imageHeight, 1.0)
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            centered_image = Table([[image]], colWidths=[doc.width])
            centered_image.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(Spacer(1, 1 * mm))
            story.append(centered_image)
            if caption:
                story.append(Paragraph(paragraph_markup(caption), caption_style))

        choices = question.get("choices") or []
        for choice in choices:
            if isinstance(choice, dict):
                label = choice.get("label", "")
                text = first_value(choice, ["text_markdown", "text", "content"], "")
                story.append(Paragraph(paragraph_markup(f"({label}) {text}"), option_style))
            else:
                story.append(Paragraph(paragraph_markup(str(choice)), option_style))

        if show_answers:
            answer = question.get("answer")
            if answer is None:
                answer = first_value(question, ["solution_markdown", "explanation"], "")
            if answer:
                story.extend([Spacer(1, 3 * mm), Paragraph("Answer / solution", small_style), Paragraph(paragraph_markup(answer_text(answer)), answer_style)])
        else:
            story.extend([Spacer(1, 3 * mm), Paragraph("Response:", small_style)])
            for _ in range(3 if not image_refs else 2):
                story.extend([Spacer(1, 6 * mm), Table([[""]], colWidths=[doc.width], rowHeights=[1]), Spacer(1, 1 * mm)])
        if index != len(selected):
            story.append(PageBreak())

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, canvasmaker=NumberedCanvas)


def parse_ids(args: argparse.Namespace) -> list[str]:
    ids = []
    if args.question_ids:
        ids.extend(item.strip() for item in args.question_ids.split(",") if item.strip())
    if args.ids_file:
        ids.extend(line.strip() for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))
    if not ids:
        raise ValueError("Provide --question-ids or --ids-file; refusing to export an unselected bank")
    if len(ids) != len(set(ids)):
        raise ValueError("The selected question IDs contain duplicates")
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--template", type=Path, help="Template PDF used for provenance/A4 validation")
    parser.add_argument("--question-ids")
    parser.add_argument("--ids-file", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--answers-output", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--student-name", default="")
    parser.add_argument("--show-source", action="store_true")
    parser.add_argument("--font", help="Legacy alias for --question-font-path")
    parser.add_argument("--question-font-path", help="TrueType/OpenType font for question stems and metadata")
    parser.add_argument("--option-font-path", help="TrueType/OpenType font for multiple-choice options")
    args = parser.parse_args()

    try:
        if args.template and not args.template.exists():
            raise FileNotFoundError(f"Template PDF not found: {args.template}")
        data, question_index, asset_index = load_bank(args.manifest)
        ids = parse_ids(args)
        unknown = [qid for qid in ids if qid not in question_index]
        if unknown:
            raise ValueError(f"Unknown question IDs: {', '.join(unknown)}")
        selected = [question_index[qid] for qid in ids]
        collection = data.get("collection", {}) if isinstance(data.get("collection", {}), dict) else {}
        title = args.title or first_value(data.get("assignment", {}) if isinstance(data.get("assignment", {}), dict) else {}, ["title"], "") or first_value(collection, ["template_title", "title", "course"], "Physics Homework")
        question_font_path = args.question_font_path or args.font
        build_pdf(args.output, data, selected, args.manifest.parent, asset_index, title, args.student_name, args.show_source, False, question_font_path, args.option_font_path)
        if args.answers_output:
            build_pdf(args.answers_output, data, selected, args.manifest.parent, asset_index, title, args.student_name, args.show_source, True, question_font_path, args.option_font_path)
        print(f"Created {args.output} ({len(selected)} questions)")
        if args.answers_output:
            print(f"Created {args.answers_output}")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report one clean actionable error
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
