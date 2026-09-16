#!/usr/bin/env python3
"""Post-build structural validator for homework-pdf v2 outputs."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import fitz

A4_W, A4_H = 595.276, 841.890
FOOTER = "Mike's Physics - Pocket Cosmos"


def validate(pdf: Path, report: Path | None = None) -> dict:
    errors, warnings = [], []
    if not pdf.is_file() or pdf.stat().st_size < 1000:
        return {"status": "error", "errors": [f"missing or implausibly small PDF: {pdf}"], "warnings": []}
    doc = fitz.open(pdf)
    if not doc.page_count:
        errors.append("PDF has zero pages")
    texts = []
    for idx, page in enumerate(doc, start=1):
        rect = page.rect
        if abs(rect.width - A4_W) > 3 or abs(rect.height - A4_H) > 3:
            errors.append(f"page {idx}: not A4 portrait ({rect.width:.1f}x{rect.height:.1f})")
        text = page.get_text("text")
        texts.append(text)
        if FOOTER not in text:
            errors.append(f"page {idx}: footer missing")
        if not re.search(rf"Page\s+{idx}\s+of\s+{doc.page_count}\b", text):
            errors.append(f"page {idx}: page-number footer missing or wrong")
    build = None
    if report:
        if not report.exists():
            errors.append(f"build report missing: {report}")
        else:
            build = json.loads(report.read_text(encoding="utf-8"))
            if Path(build.get("output", "")).name != pdf.name:
                warnings.append("build report output path does not match validated PDF basename")
            if not build.get("selected_ids"):
                errors.append("build report has no selected_ids")
            if build.get("warnings"):
                warnings.extend(build["warnings"])
    return {"status": "ok" if not errors else "error", "errors": errors, "warnings": warnings, "pages": doc.page_count, "build_report": build}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("pdf", type=Path); ap.add_argument("--build-report", type=Path); ap.add_argument("--report", type=Path)
    args = ap.parse_args(); result = validate(args.pdf, args.build_report)
    if args.report: args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for w in result["warnings"]: print(f"WARNING: {w}")
    for e in result["errors"]: print(f"ERROR: {e}")
    return 0 if result["status"] == "ok" else 1

if __name__ == "__main__": raise SystemExit(main())
