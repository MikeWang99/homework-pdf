#!/usr/bin/env python3
import base64
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

ROOT = Path(__file__).parents[1]

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

B = load("builder", "build_homework_pdf.py")
V = load("validator", "validate_homework.py")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAIAAAACUFjqAAAAFElEQVR4nGP8z4APMOGVHbHSAEEsAROxCnMTAAAAAElFTkSuQmCC")

class BuilderTests(unittest.TestCase):
    def test_choice_asset_metadata_is_preserved_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); img = root / "a.png"; img.write_bytes(PNG)
            q = {"id":"q1","stem":"Pick the graph.","choices":[{"label":"A","text":""},{"label":"B","text":"none"}],"asset_ids":["a"]}
            assets = {"a":{"id":"a","file":"a.png","role":"choice","choice_label":"A"}}
            resolved = B.resolve_assets(q, root, assets)
            self.assertEqual(resolved[0]["role"], "choice"); self.assertEqual(resolved[0]["choice_label"], "A")
            self.assertEqual(B.validate_question(q, root, assets), [])

    def test_choice_asset_without_label_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/"a.png").write_bytes(PNG)
            q={"id":"q1","stem":"x","choices":[{"label":"A","text":"x"}],"asset_ids":["a"]}
            assets={"a":{"id":"a","file":"a.png","role":"choice"}}
            with self.assertRaises(ValueError): B.validate_question(q, root, assets)

    def test_unsupported_latex_fails(self):
        q={"id":"q1","stem":r"Use $\\begin{cases}x\\end{cases}$","asset_ids":[]}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): B.validate_question(q, Path(tmp), {})

    def test_build_and_post_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"a.png").write_bytes(PNG)
            manifest=root/"questions.json"; out=root/"homework.pdf"; report=root/"build.json"
            manifest.write_text(json.dumps({"collection":{"title":"Physics"},"questions":[{"id":"q1","stem":"What is $\\Delta U$?","choices":[{"label":"A","text":"Energy"}],"asset_ids":["a"]}],"assets":[{"id":"a","file":"a.png","role":"stem"}]}))
            data,qidx,aidx=B.load_bank(manifest)
            r=B.build_pdf(out,data,[qidx["q1"]],root,aidx,"Physics","",False,False,None,None,"")
            report.write_text(json.dumps({"output":str(out),"selected_ids":["q1"],**r}))
            result=V.validate(out,report)
            self.assertEqual(result["status"],"ok", result)
            self.assertGreater(fitz.open(out).page_count,0)

    def test_template_must_be_a4(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.pdf"
            doc=fitz.open(); doc.new_page(width=400,height=400); doc.save(path)
            with self.assertRaises(ValueError): B.validate_template(path)

    def test_display_math_common_commands_are_supported(self):
        text=r"Energy is $$\frac{1}{2}mv^2$$ and $\sum_i F_i=ma$."
        self.assertEqual(B.find_unsupported_latex(text), [])

if __name__ == "__main__": unittest.main()
