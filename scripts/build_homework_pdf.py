#!/usr/bin/env python3
"""Build a deterministic, validated physics homework PDF from question-bank v2 records."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    KeepTogether,
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
MAX_IMAGE_WIDTH = 92 * mm
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
SUPPORTED_LATEX_COMMANDS = {
    "frac", "sqrt", "mathrm", "text", "textrm", "operatorname", "vec", "hat", "bar",
    "propto", "times", "cdot", "ldots", "cdots", "Omega", "Delta", "theta", "pi",
    "alpha", "beta", "gamma", "lambda", "mu", "rho", "sigma", "phi", "omega",
    "le", "leq", "ge", "geq", "pm", "neq", "approx", "infty", "int", "sum", "prod",
    "partial", "nabla", "sin", "cos", "tan", "ln", "log", "exp", ",", ";", "!",
}


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


def explicit_subquestions(question: dict) -> list[dict[str, str]]:
    def label(item, idx):
        if isinstance(item, dict):
            value = first_value(item, ["label", "number", "id", "part", "name"], "")
            if value:
                return str(value).strip()
        return f"({chr(96 + idx)})" if idx <= 26 else f"({idx})"

    def text(item):
        if isinstance(item, dict):
            value = first_value(item, ["text_markdown", "text", "prompt", "question", "stem", "content", "body"], "")
            if isinstance(value, list):
                return "\n".join(str(v) for v in value)
            return str(value)
        return str(item)

    for key in ("subquestions", "question_parts", "parts"):
        raw = question.get(key)
        if not raw:
            continue
        if isinstance(raw, dict):
            raw = [{"label": k, "text": v} for k, v in raw.items()]
        if not isinstance(raw, list):
            continue
        out = []
        for idx, item in enumerate(raw, start=1):
            value = text(item).strip()
            if value:
                out.append({"label": label(item, idx), "text": value})
        if out:
            return out
    return []


INLINE_PART_RE = re.compile(
    r"(?m)^[ \t]*(?:"
    r"(?P<chinese>第[一二三四五六七八九十百\d]+小问)(?:[：:.)、，,]?\s*)"
    r"|(?P<label>(?:[（(]\s*(?:[A-Za-z]+|\d+)\s*[）)])|(?:[A-Za-z]+|\d+)[.)：:-]|(?:[IVXLCDM]+|\d+)(?=\s))\s*(?:[.)：:-]\s*|\s+))"
)


def split_inline_subquestions(text: str) -> tuple[str, list[dict[str, str]]]:
    matches = list(INLINE_PART_RE.finditer(text))
    if not matches:
        return text.strip(), []
    bare = [m for m in matches if m.group("label") and re.fullmatch(r"[IVXLCDM]+|\d+", m.group("label").strip())]
    if len(matches) == 1 and bare:
        return text.strip(), []
    parts = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        if body:
            parts.append({"label": (match.group("label") or match.group("chinese")).strip(), "text": body})
    if not parts:
        return text.strip(), []
    return text[:matches[0].start()].strip(), parts


def question_sections(question: dict) -> tuple[str, list[dict[str, str]]]:
    stem = question_text(question)
    parts = explicit_subquestions(question)
    return (stem.strip(), parts) if parts else split_inline_subquestions(stem)


def layout_block_kind(block: dict) -> str:
    """Normalize the compact and explicit layout-block spellings."""
    if not isinstance(block, dict):
        return ""
    if block.get("type"):
        return str(block["type"]).strip().lower()
    if block.get("asset_id"):
        return "figure"
    if block.get("spacer_lines") is not None:
        return "response_space"
    if block.get("text") is not None:
        return "text"
    return ""


def question_layout_blocks(question: dict) -> list[dict]:
    raw = question.get("layout_blocks")
    if raw in (None, ""):
        return []
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{question.get('id', '<unknown>')}: layout_blocks must be a non-empty list")
    return raw


def points_for(question: dict) -> float:
    try:
        return float(first_value(question, ["points", "official_marks", "marks"], 0))
    except (TypeError, ValueError):
        return 0.0


def format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def find_unsupported_latex(text: str) -> list[str]:
    commands = set(re.findall(r"\\([A-Za-z]+|[,;!])", text or ""))
    return sorted(commands - SUPPORTED_LATEX_COMMANDS)


def _simple_fraction(text: str) -> str:
    pattern = re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}")
    old = None
    while old != text:
        old = text
        text = pattern.sub(r"(\1)/(\2)", text)
    return text


def format_inline_math(text: str) -> str:
    text = _simple_fraction(text)
    text = re.sub(r"\\(?:mathrm|text|textrm|operatorname)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)
    text = re.sub(r"\\(?:vec|hat|bar)\{([^{}]+)\}", r"\1", text)
    replacements = {
        r"\propto": "∝", r"\times": "×", r"\cdot": "·", r"\ldots": "…", r"\cdots": "⋯",
        r"\Omega": "Ω", r"\Delta": "Δ", r"\theta": "θ", r"\pi": "π", r"\alpha": "α",
        r"\beta": "β", r"\gamma": "γ", r"\lambda": "λ", r"\mu": "μ", r"\rho": "ρ",
        r"\sigma": "σ", r"\phi": "φ", r"\omega": "ω", r"\leq": "≤", r"\le": "≤",
        r"\geq": "≥", r"\ge": "≥", r"\pm": "±", r"\neq": "≠", r"\approx": "≈",
        r"\infty": "∞", r"\int": "∫", r"\sum": "Σ", r"\prod": "Π", r"\partial": "∂",
        r"\nabla": "∇", r"\sin": "sin", r"\cos": "cos", r"\tan": "tan", r"\ln": "ln",
        r"\log": "log", r"\exp": "exp", r"\,": " ", r"\;": " ", r"\!": "",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", text)
    text = re.sub(r"_([A-Za-z0-9+-]+)", r"<sub>\1</sub>", text)
    text = re.sub(r"\^\{([^{}]+)\}", r"<super>\1</super>", text)
    text = re.sub(r"\^([A-Za-z0-9+-]+)", r"<super>\1</super>", text)
    return text


def paragraph_markup(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = escape(text)
    text = re.sub(r"\$([^$\n]+)\$", lambda m: f"<i>{format_inline_math(m.group(1))}</i>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    return text.replace("\n", "<br/>")


def markdown_flowables(text: str, style: ParagraphStyle, display_style: ParagraphStyle) -> list:
    """Render Markdown text with explicit $$...$$ display-math blocks."""
    parts = re.split(r"(\$\$.*?\$\$)", text or "", flags=re.S)
    out = []
    for part in parts:
        if not part:
            continue
        if part.startswith("$$") and part.endswith("$$"):
            math = part[2:-2].strip()
            out.append(Paragraph(f"<i>{format_inline_math(escape(math))}</i>", display_style))
        elif part.strip():
            out.append(Paragraph(paragraph_markup(part.strip()), style))
    return out


def answer_text(answer) -> str:
    if answer is None:
        return ""
    if isinstance(answer, str):
        return answer
    if isinstance(answer, list):
        return "\n".join(f"- {item}" for item in answer)
    if isinstance(answer, dict):
        preferred = ["summary", "final", "answer", "mark_points", "parts", "explanation", "text", "label"]
        keys = [k for k in preferred if k in answer] + sorted(k for k in answer if k not in preferred)
        chunks = []
        for key in keys:
            value = answer[key]
            if value is None:
                continue
            if isinstance(value, list):
                value = "\n".join(f"- {item}" for item in value)
            elif isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            chunks.append(f"{key}: {value}")
        return "\n".join(chunks)
    return str(answer)


def load_bank(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise ValueError("The manifest must contain a top-level questions array")
    qindex = {}
    for q in questions:
        qid = q.get("id")
        if not qid or qid in qindex:
            raise ValueError(f"Every question needs a unique id; duplicate/missing id: {qid!r}")
        qindex[qid] = q
    asset_records = list(data.get("assets", []))
    for candidate in (path.parent / "assets.json", path.parent / "asset_manifest.json", path.parent / "manifests" / "asset_manifest.json"):
        if not asset_records and candidate.exists():
            external = json.loads(candidate.read_text(encoding="utf-8"))
            asset_records = external.get("assets", [])
            break
    aindex = {a.get("id"): a for a in asset_records if a.get("id")}
    return data, qindex, aindex


def _resolve_path(raw: str, root: Path, qid: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise FileNotFoundError(f"Image for {qid} not found: {path}")
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
        raise ValueError(f"Unsupported image format {path.suffix!r}; rasterize to PNG/JPG first")
    return path


def resolve_assets(question: dict, bank_root: Path, asset_index: dict[str, dict]) -> list[dict]:
    refs: list[dict] = []
    for asset_id in question.get("asset_ids") or []:
        record = asset_index.get(asset_id)
        if not record:
            raise FileNotFoundError(f"Asset id {asset_id!r} is not present in the asset manifest")
        refs.append(dict(record))
    if not refs:
        assets = question.get("assets") or []
        if isinstance(assets, dict):
            assets = [assets]
        for item in assets:
            if isinstance(item, str):
                refs.append({"file": item, "role": "stem"})
            else:
                refs.append(dict(item))
    if not refs and isinstance(question.get("asset"), str):
        refs.append({"file": question["asset"], "role": "stem"})

    resolved = []
    for item in refs:
        raw = item.get("file") or item.get("path") or item.get("asset")
        if not raw:
            raise FileNotFoundError(f"Question {question.get('id')} has an empty image reference")
        item["path_resolved"] = _resolve_path(raw, bank_root, question.get("id", "?"))
        item["role"] = item.get("role") or "stem"
        item["caption"] = item.get("alt") or item.get("caption") or ""
        resolved.append(item)
    return resolved


def validate_template(path: Path | None) -> dict:
    if path is None:
        return {"status": "not-supplied"}
    if not path.exists():
        raise FileNotFoundError(f"Template PDF not found: {path}")
    doc = fitz.open(path)
    if not doc.page_count:
        raise ValueError("Template PDF has no pages")
    rect = doc[0].rect
    expected_w, expected_h = PAGE_W, PAGE_H
    if abs(rect.width - expected_w) > 3 or abs(rect.height - expected_h) > 3:
        raise ValueError(f"Template is not A4 portrait: {rect.width:.1f}x{rect.height:.1f} pt")
    return {"status": "validated", "page_width": round(rect.width, 2), "page_height": round(rect.height, 2), "pages": doc.page_count}


def validate_question(q: dict, bank_root: Path, asset_index: dict[str, dict]) -> list[str]:
    warnings = []
    qid = q.get("id", "<unknown>")
    stem = question_text(q).strip()
    context = str(q.get("context") or "").strip()
    if not stem and not context:
        raise ValueError(f"{qid}: empty question text")
    unsupported = find_unsupported_latex("\n".join([context, stem] + [str(c.get("text", "")) for c in q.get("choices") or [] if isinstance(c, dict)]))
    if unsupported:
        raise ValueError(f"{qid}: unsupported LaTeX commands: {', '.join('\\'+c for c in unsupported)}")
    assets = resolve_assets(q, bank_root, asset_index)
    choice_labels = {str(c.get("label")) for c in q.get("choices") or [] if isinstance(c, dict) and c.get("label") is not None}
    for asset in assets:
        role = asset.get("role")
        if role not in {"stem", "shared", "choice"}:
            raise ValueError(f"{qid}: unsupported asset role {role!r}")
        if asset.get("role") == "choice":
            label = str(asset.get("choice_label") or "")
            if not label:
                raise ValueError(f"{qid}: choice asset missing choice_label")
            if label not in choice_labels:
                raise ValueError(f"{qid}: choice asset label {label!r} has no matching choice")
    blocks = question_layout_blocks(q)
    if blocks:
        by_id = {str(asset.get("id")): asset for asset in assets if asset.get("id")}
        placed_figures = []
        has_text = False
        for block in blocks:
            kind = layout_block_kind(block)
            if kind == "text":
                if not str(block.get("text") or "").strip():
                    raise ValueError(f"{qid}: layout text block is empty")
                has_text = True
            elif kind == "figure":
                asset_id = str(block.get("asset_id") or "")
                if not asset_id or asset_id not in by_id:
                    raise ValueError(f"{qid}: layout figure references unknown asset {asset_id!r}")
                asset = by_id[asset_id]
                if asset.get("role") not in {"stem", "shared"}:
                    raise ValueError(f"{qid}: layout figure {asset_id!r} must have role stem/shared")
                placed_figures.append(asset_id)
                max_height = block.get("max_height_mm", asset.get("max_height_mm"))
                if max_height is not None:
                    try:
                        if float(max_height) <= 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        raise ValueError(f"{qid}: layout figure {asset_id!r} has invalid max_height_mm")
            elif kind == "response_space":
                try:
                    if float(block.get("lines", block.get("spacer_lines", 1))) < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    raise ValueError(f"{qid}: response_space lines must be a non-negative number")
            else:
                raise ValueError(f"{qid}: unsupported layout block type {kind!r}")
        if not has_text:
            raise ValueError(f"{qid}: layout_blocks must contain a text block")
        if len(placed_figures) != len(set(placed_figures)):
            raise ValueError(f"{qid}: layout figure assets may only be placed once")
        expected_figures = {str(asset.get("id")) for asset in assets if asset.get("role") in {"stem", "shared"}}
        if set(placed_figures) != expected_figures:
            missing = sorted(expected_figures - set(placed_figures))
            extra = sorted(set(placed_figures) - expected_figures)
            detail = []
            if missing: detail.append(f"missing {', '.join(missing)}")
            if extra: detail.append(f"unexpected {', '.join(extra)}")
            raise ValueError(f"{qid}: layout figure coverage mismatch ({'; '.join(detail)})")
    return warnings


class NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
    def save(self):
        count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.saveState(); self.setFont("Helvetica", 8); self.setFillColor(colors.HexColor("#222222"))
            self.drawRightString(PAGE_W - MARGIN_X, FOOTER_Y, f"Page {self._pageNumber} of {count}"); self.restoreState()
            super().showPage()
        super().save()


def draw_header_footer(canvas, doc, title, total, score, accuracy, student):
    canvas.saveState(); canvas.setFillColor(colors.black); canvas.setFont("Helvetica", 12)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 14 * mm, title)
    canvas.setLineWidth(0.5); canvas.line(MARGIN_X, PAGE_H - 18 * mm, PAGE_W - MARGIN_X, PAGE_H - 18 * mm)
    if canvas.getPageNumber() == 1:
        canvas.setFont("Helvetica", 8.7)
        canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 26 * mm, f"Total Points: {total}    Score: {score}    Accuracy: {accuracy} %")
    if student:
        canvas.setFont("Helvetica", 8.5); canvas.drawString(MARGIN_X, PAGE_H - 26 * mm, f"Student: {student}")
    canvas.line(MARGIN_X, 14 * mm, PAGE_W - MARGIN_X, 14 * mm); canvas.setFont("Helvetica", 8.5)
    canvas.drawCentredString(PAGE_W / 2, FOOTER_Y, DEFAULT_FOOTER); canvas.restoreState()


def register_local_font(path: str | None, name: str) -> str | None:
    if not path:
        return None
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"Font not found: {file}")
    pdfmetrics.registerFont(TTFont(name, str(file)))
    return name


def image_flowable(asset: dict, doc_width: float, max_height: float, caption_style: ParagraphStyle):
    image = RLImage(str(asset["path_resolved"]))
    source_width = asset.get("source_width_pt")
    source_height = asset.get("source_height_pt")
    if source_width and source_height:
        scale = min(float(source_width) / image.imageWidth, float(source_height) / image.imageHeight)
    else:
        scale = min(MAX_IMAGE_WIDTH / image.imageWidth, doc_width * 0.96 / image.imageWidth, max_height / image.imageHeight, 1.0)
    image.drawWidth *= scale; image.drawHeight *= scale
    table = Table([[image]], colWidths=[doc_width])
    table.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    out = [Spacer(1, 1 * mm), table]
    if asset.get("caption"):
        out.append(Paragraph(paragraph_markup(asset["caption"]), caption_style))
    return out, image.drawHeight


def build_pdf(output: Path, data: dict, selected: list[dict], bank_root: Path, asset_index: dict[str, dict], title: str,
              student: str, show_source: bool, show_answers: bool, question_font_path: str | None,
              option_font_path: str | None, front_matter: str) -> dict:
    question_font = register_local_font(question_font_path, "LocalHomeworkQuestionFont") or "Helvetica"
    option_font = register_local_font(option_font_path, "LocalHomeworkOptionFont") or "Times-Roman"
    assignment = data.get("assignment", {}) if isinstance(data.get("assignment"), dict) else {}
    total_raw = assignment.get("total_points")
    has_points = any(first_value(q, ["points", "official_marks", "marks"], None) is not None for q in selected)
    # Leave the field blank when the selected bank records do not provide
    # point values; do not render a dash as a student-facing placeholder.
    total = format_number(sum(points_for(q) for q in selected)) if total_raw in (None, "") and has_points else ("" if total_raw in (None, "") else str(total_raw))
    score, accuracy = str(assignment.get("score", "")), str(assignment.get("accuracy", ""))

    doc = BaseDocTemplate(str(output), pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="homework", frames=frame, onPage=lambda c,d: draw_header_footer(c,d,title,total,score,accuracy,student))])
    styles = getSampleStyleSheet()
    qstyle = ParagraphStyle("question", parent=styles["BodyText"], fontName=question_font, fontSize=11, leading=15, textColor=colors.black, spaceAfter=3*mm)
    option_style = ParagraphStyle("option", parent=styles["BodyText"], fontName=option_font, fontSize=11, leading=15, textColor=colors.black, spaceAfter=1.5*mm)
    part_style = ParagraphStyle("subquestion", parent=qstyle, leftIndent=5*mm, firstLineIndent=-5*mm, spaceAfter=2.2*mm)
    source_style = ParagraphStyle("source", parent=qstyle, fontSize=8.2, leading=11, textColor=colors.HexColor("#476477"), spaceAfter=2*mm)
    caption_style = ParagraphStyle("caption", parent=qstyle, fontSize=8, leading=10, textColor=colors.HexColor("#476477"), alignment=TA_LEFT)
    display_style = ParagraphStyle("display_math", parent=qstyle, alignment=TA_CENTER, fontSize=11, leading=15, spaceAfter=2*mm)
    answer_style = ParagraphStyle("answer", parent=qstyle, fontSize=9.5, leading=13, textColor=colors.HexColor("#12344D"), backColor=colors.HexColor("#F3F7F9"), borderColor=colors.HexColor("#B7C8D2"), borderWidth=.5, borderPadding=7)
    small_style = ParagraphStyle("small", parent=qstyle, fontSize=8.5, leading=11)

    story = []
    if front_matter.strip():
        front_style = ParagraphStyle("front", parent=qstyle, fontSize=13, leading=22, alignment=TA_CENTER, borderColor=colors.HexColor("#12344D"), borderWidth=.75, borderPadding=16)
        story.extend([Spacer(1, 10*mm), Paragraph(paragraph_markup(front_matter.strip()), front_style), PageBreak()])

    warnings = []
    for index, q in enumerate(selected, start=1):
        warnings.extend(validate_question(q, bank_root, asset_index))
        assets = resolve_assets(q, bank_root, asset_index)
        stem_assets = [a for a in assets if a.get("role") in {"stem", "shared"}]
        choice_assets = {}
        for a in assets:
            if a.get("role") == "choice":
                choice_assets.setdefault(str(a.get("choice_label")), []).append(a)
        source = q.get("source", {}) if isinstance(q.get("source"), dict) else {}
        context = str(q.get("context") or "").strip()
        stem, subquestions = question_sections(q)
        choices = q.get("choices") or []
        layout_blocks = question_layout_blocks(q)

        if layout_blocks:
            assets_by_id = {str(asset.get("id")): asset for asset in assets if asset.get("id")}
            first_text = True
            total_layout_image_height = 0.0
            for block in layout_blocks:
                kind = layout_block_kind(block)
                if kind == "text":
                    prefix = f"{index}. " if first_text else ""
                    story.extend(markdown_flowables(prefix + str(block["text"]), qstyle, display_style))
                    first_text = False
                elif kind == "figure":
                    asset = assets_by_id[str(block["asset_id"])]
                    max_height_mm = block.get("max_height_mm", asset.get("max_height_mm", 135))
                    flows, height = image_flowable(asset, doc.width, float(max_height_mm) * mm, caption_style)
                    story.extend(flows)
                    total_layout_image_height += height
                elif kind == "response_space":
                    lines = float(block.get("lines", block.get("spacer_lines", 1)))
                    story.append(Spacer(1, lines * qstyle.leading))
            if show_answers:
                answer = q.get("answer")
                if answer is None: answer = first_value(q, ["solution_markdown", "explanation"], "")
                if answer:
                    story.extend([Spacer(1, 3*mm), Paragraph("Answer / solution", small_style), Paragraph(paragraph_markup(answer_text(answer)), answer_style)])
            elif not choices and index < len(selected):
                # Layout blocks normally contain per-subquestion response space;
                # reserve a compact final buffer before the next question.
                story.append(Spacer(1, 24*mm))
            story.append(Spacer(1, 3*mm))
            continue

        bundle = []
        if show_source and source:
            source_doc = first_value(source, ["document", "file"], "")
            pages = q.get("source_pages") or [first_value(source, ["pdf_page", "source_page", "page"], "")]
            pages_text = ",".join(str(p) for p in pages if p not in (None, ""))
            source_line = " · ".join(v for v in [str(source_doc) if source_doc else "", f"pages {pages_text}" if pages_text else ""] if v)
            if source_line: bundle.append(Paragraph(paragraph_markup(source_line), source_style))
        if context:
            bundle.extend(markdown_flowables(context, qstyle, display_style))
        if stem:
            bundle.extend(markdown_flowables(f"{index}. {stem}", qstyle, display_style))
        else:
            bundle.append(Paragraph(f"{index}.", qstyle))
        for part in subquestions:
            bundle.extend(markdown_flowables(f"**{part['label']}** {part['text']}", part_style, display_style))
            if not choices:
                # One additional unruled line after every FRQ subquestion.
                bundle.append(Spacer(1, qstyle.leading))
        total_stem_image_height = 0.0
        per_image_cap = min(135*mm, (145*mm / max(1, len(stem_assets))))
        for asset in stem_assets:
            flows, h = image_flowable(asset, doc.width, per_image_cap, caption_style); bundle.extend(flows); total_stem_image_height += h
        question_flowables = list(bundle)
        for choice in choices:
            if isinstance(choice, dict):
                label = str(choice.get("label", "")); text = str(first_value(choice, ["text_markdown", "text", "content"], ""))
                choice_bundle = [Paragraph(paragraph_markup(f"({label}) {text}"), option_style)]
                for asset in choice_assets.get(label, []):
                    flows, _ = image_flowable(asset, doc.width, 55*mm, caption_style); choice_bundle.extend(flows)
                question_flowables.extend(choice_bundle)
            else:
                question_flowables.append(Paragraph(paragraph_markup(str(choice)), option_style))
        story.append(KeepTogether(question_flowables))

        if show_answers:
            answer = q.get("answer")
            if answer is None: answer = first_value(q, ["solution_markdown", "explanation"], "")
            if answer:
                story.extend([Spacer(1, 3*mm), Paragraph("Answer / solution", small_style), Paragraph(paragraph_markup(answer_text(answer)), answer_style)])
        elif not choices and index < len(selected):
            blank_height = max(24*mm, min(80*mm, 18*mm + 0.35*total_stem_image_height))
            story.append(Spacer(1, blank_height))
        story.append(Spacer(1, 3*mm))

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, canvasmaker=NumberedCanvas)
    return {"warnings": warnings, "question_count": len(selected), "selected_ids": [q["id"] for q in selected]}


def parse_ids(args) -> list[str]:
    ids = []
    if args.question_ids: ids.extend(v.strip() for v in args.question_ids.split(",") if v.strip())
    if args.ids_file: ids.extend(line.strip() for line in args.ids_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))
    if not ids: raise ValueError("Provide --question-ids or --ids-file; refusing to export an unselected bank")
    if len(ids) != len(set(ids)): raise ValueError("The selected question IDs contain duplicates")
    return ids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, type=Path); ap.add_argument("--template", type=Path)
    ap.add_argument("--question-ids"); ap.add_argument("--ids-file", type=Path); ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--answers-output", type=Path); ap.add_argument("--title"); ap.add_argument("--student-name", default="")
    ap.add_argument("--front-matter", type=Path); ap.add_argument("--show-source", action="store_true")
    ap.add_argument("--font", help="Legacy alias for --question-font-path"); ap.add_argument("--question-font-path"); ap.add_argument("--option-font-path")
    ap.add_argument("--report", type=Path, help="Write machine-readable build report")
    args = ap.parse_args()
    try:
        template_report = validate_template(args.template)
        data, qindex, aindex = load_bank(args.manifest)
        ids = parse_ids(args); unknown = [qid for qid in ids if qid not in qindex]
        if unknown: raise ValueError(f"Unknown question IDs: {', '.join(unknown)}")
        selected = [qindex[qid] for qid in ids]
        collection = data.get("collection", {}) if isinstance(data.get("collection"), dict) else {}
        title = args.title or first_value(data.get("assignment", {}) if isinstance(data.get("assignment"), dict) else {}, ["title"], "") or first_value(collection, ["template_title", "title", "course"], "Physics Homework")
        front = args.front_matter.read_text(encoding="utf-8") if args.front_matter else ""
        font = args.question_font_path or args.font
        report = build_pdf(args.output, data, selected, args.manifest.parent, aindex, title, args.student_name, args.show_source, False, font, args.option_font_path, front)
        if args.answers_output:
            build_pdf(args.answers_output, data, selected, args.manifest.parent, aindex, title, args.student_name, args.show_source, True, font, args.option_font_path, front)
        result = {"schema_version": "2.0", "output": str(args.output), "answers_output": str(args.answers_output) if args.answers_output else None, "title": title, "template": template_report, **report}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(f"Created {args.output} ({len(selected)} questions)")
        if args.answers_output: print(f"Created {args.answers_output}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

if __name__ == "__main__":
    raise SystemExit(main())
