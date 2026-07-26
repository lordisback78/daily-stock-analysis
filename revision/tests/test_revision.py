#!/usr/bin/env python3
"""Tests de l'application de révision : python3 -m unittest discover revision/tests"""
import io
import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_TMP = tempfile.mkdtemp(prefix="revision-tests-")
os.environ["REVISION_DATA_DIR"] = _TMP

from revision.server import app, extract, srs, store  # noqa: E402


class TestSrs(unittest.TestCase):
    def test_new_card_graduates_after_learning_steps(self):
        card = srs.new_srs()
        self.assertEqual(card["state"], "new")
        card = srs.review(card, "good")
        self.assertEqual(card["state"], "learning")
        card = srs.review(card, "good")
        self.assertEqual(card["state"], "review")
        self.assertGreaterEqual(card["interval"], 1)

    def test_easy_graduates_immediately(self):
        card = srs.review(srs.new_srs(), "easy")
        self.assertEqual(card["state"], "review")
        self.assertEqual(card["interval"], 4)

    def test_again_resets_and_counts_lapse(self):
        card = srs.review(srs.review(srs.new_srs(), "good"), "good")
        card = srs.review(card, "good")  # 2e répétition -> 6 jours
        self.assertEqual(card["interval"], 6)
        lapsed = srs.review(card, "again")
        self.assertEqual(lapsed["state"], "learning")
        self.assertEqual(lapsed["lapses"], 1)
        self.assertLess(lapsed["ease"], card["ease"])

    def test_intervals_grow_and_ease_is_clamped(self):
        card = srs.review(srs.review(srs.new_srs(), "good"), "good")
        intervals = []
        for _ in range(5):
            card = srs.review(card, "good")
            intervals.append(card["interval"])
        self.assertEqual(intervals, sorted(intervals))
        hard = srs.new_srs()
        for _ in range(30):
            hard = srs.review(hard, "again")
        self.assertGreaterEqual(hard["ease"], srs.MIN_EASE)

    def test_preview_has_four_labels(self):
        preview = srs.preview_intervals(srs.new_srs())
        self.assertEqual(set(preview), {"again", "hard", "good", "easy"})


class TestExtract(unittest.TestCase):
    def test_docx(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("word/document.xml",
                        "<w:document><w:p><w:r><w:t>Titre du cours</w:t></w:r></w:p>"
                        "<w:p><w:r><w:t>La photosynth&#232;se est un processus.</w:t></w:r></w:p></w:document>")
        result = extract.extract("cours.docx", buffer.getvalue())
        self.assertIn("Titre du cours", result["text"])
        self.assertIn("photosynthèse", result["text"])
        self.assertFalse(result["needs_ai"])

    def test_pptx_orders_slides(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            for index in (10, 2, 1):
                zf.writestr(f"ppt/slides/slide{index}.xml", f"<p:sld><a:p><a:t>Diapo {index}</a:t></a:p></p:sld>")
        text = extract.extract("deck.pptx", buffer.getvalue())["text"]
        self.assertLess(text.index("Diapo 1"), text.index("Diapo 2"))
        self.assertLess(text.index("Diapo 2"), text.index("Diapo 10"))

    def test_markdown_passthrough(self):
        result = extract.extract("notes.md", "# Chapitre 1\nContenu".encode())
        self.assertEqual(result["kind"], "md")
        self.assertIn("Chapitre 1", result["text"])

    def test_image_needs_ai(self):
        result = extract.extract("tableau.jpg", b"\xff\xd8\xff")
        self.assertTrue(result["needs_ai"])
        self.assertEqual(result["media_type"], "image/jpeg")

    def test_pdf_without_text_layer_needs_ai(self):
        result = extract.extract("scan.pdf", b"%PDF-1.4\n" + b"\x00" * 200)
        self.assertTrue(result["needs_ai"])
        self.assertEqual(result["media_type"], "application/pdf")

    def test_pdf_with_text_operators(self):
        content = b"BT (Le theoreme de Thales enonce que) Tj T* (les rapports sont egaux dans un triangle.) Tj ET"
        pdf = b"%PDF-1.4\nstream\n" + content + b"\nendstream\n" + b"x" * 400
        result = extract.extract("cours.pdf", pdf)
        self.assertIn("theoreme de Thales", result["text"])
        self.assertTrue(result["needs_ai"])  # texte court -> l'IA ferait mieux


COURSE = """# La photosynthese

Photosynthese : processus par lequel les plantes convertissent la lumiere en energie chimique.
Chlorophylle : pigment vert qui capte l'energie lumineuse dans les chloroplastes.

- Elle se deroule dans les chloroplastes
- Elle produit du glucose et du dioxygene

La phase claire a lieu dans les thylakoides et produit de l'ATP et du NADPH, qui alimentent
ensuite le cycle de Calvin. Ce cycle fixe le dioxyde de carbone pour former des sucres,
etape indispensable a la croissance de la plante et a toute la chaine alimentaire.
"""


class TestApi(unittest.TestCase):
    """Teste les handlers directement (sans passer par HTTP)."""

    def setUp(self):
        store._cache = store._empty()
        store.save()

    def test_course_lifecycle_offline(self):
        created = app.api_course_create({}, {"text": COURSE, "title": "Photosynthèse", "subject": "SVT"})
        course_id = created["course"]["id"]
        self.assertEqual(created["course"]["title"], "Photosynthèse")

        material = app.api_course_generate(course_id, {}, {})
        self.assertTrue(material["offline"])
        self.assertGreater(material["created"], 0)

        detail = app.api_course_get(course_id, {}, {})
        self.assertEqual(len(detail["cards"]), material["created"])
        self.assertTrue(detail["course"]["fiche"])

        session = app.api_session({"scope": ["due"], "limit": ["5"]}, {})
        self.assertTrue(session["cards"])
        card = session["cards"][0]
        self.assertIn("intervals", card)

        review = app.api_review({}, {"card_id": card["id"], "grade": "good", "ms": 1200})
        self.assertEqual(review["done_today"], 1)
        self.assertEqual(review["card"]["srs"]["state"], "learning")

        stats = app.api_stats({}, {})
        self.assertEqual(stats["reviews"], 1)
        self.assertEqual(stats["accuracy"], 100)
        self.assertEqual(stats["streak"], 1)
        self.assertEqual(len(stats["forecast"]), 15)

        state = app.api_state({}, {})
        self.assertEqual(len(state["courses"]), 1)
        self.assertTrue(any(m["id"] == "daily" for m in state["missions"]))

        deleted = app.api_course_delete(course_id, {}, {})
        self.assertEqual(deleted["cards_removed"], material["created"])
        self.assertEqual(app.api_state({}, {})["courses"], [])

    def test_generation_is_idempotent_on_duplicates(self):
        course_id = app.api_course_create({}, {"text": COURSE})["course"]["id"]
        first = app.api_course_generate(course_id, {}, {})["created"]
        second = app.api_course_generate(course_id, {}, {})["created"]
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)

    def test_manual_cards_and_qcm_normalisation(self):
        course_id = app.api_course_create({}, {"text": COURSE})["course"]["id"]
        flashcard = app.api_card_create({}, {"course_id": course_id, "question": "Q ?", "answer": "R"})
        self.assertEqual(flashcard["type"], "flashcard")
        qcm = app.api_card_create({}, {
            "course_id": course_id, "type": "qcm", "question": "Combien ?",
            "choix": ["deux", "trois", "quatre"], "correct": "1",
        })
        self.assertEqual(qcm["correct"], 1)
        self.assertEqual(qcm["answer"], "trois")

        patched = app.api_card_patch(qcm["id"], {}, {"correct": 99})
        self.assertEqual(patched["correct"], 2)
        app.api_card_delete(flashcard["id"], {}, {})
        self.assertEqual(len(app.api_course_get(course_id, {}, {})["cards"]), 1)

    def test_exam_shuffles_and_keeps_correct_index(self):
        course_id = app.api_course_create({}, {"text": COURSE})["course"]["id"]
        for index in range(6):
            app.api_card_create({}, {"course_id": course_id, "type": "qcm", "question": f"Q{index} ?",
                                     "choix": ["bon", "faux1", "faux2", "faux3"], "correct": 0})
        exam = app.api_exam({}, {"course_id": course_id, "count": 6})
        self.assertEqual(len(exam["questions"]), 6)
        for question in exam["questions"]:
            self.assertEqual(question["choices"][question["correct"]], "bon")

    def test_errors(self):
        with self.assertRaises(app.ApiError):
            app.api_course_create({}, {"text": "   "})
        with self.assertRaises(app.ApiError):
            app.api_course_get("course_inconnu", {}, {})
        with self.assertRaises(app.ApiError):
            app.api_review({}, {"card_id": "x", "grade": "parfait"})

    def test_settings_round_trip(self):
        updated = app.api_settings_put({}, {"daily_goal": 45, "model": "claude-opus-5", "inconnu": 1})
        self.assertEqual(updated["daily_goal"], 45)
        self.assertNotIn("inconnu", updated)
        self.assertEqual(app.api_state({}, {})["settings"]["daily_goal"], 45)


class TestMobileParity(unittest.TestCase):
    """La version mobile réimplémente SM-2 en JS : on vérifie qu'elle ne dérive pas."""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "mobile", "app.body.html"), encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_learning_steps_match(self):
        steps = re.search(r"const STEPS = \[([^\]]+)\]", self.source).group(1)
        self.assertEqual([int(v.strip()) for v in steps.split(",")], srs.LEARNING_STEPS)

    def test_min_ease_matches(self):
        value = re.search(r"const MIN_EASE = ([\d.]+)", self.source).group(1)
        self.assertEqual(float(value), srs.MIN_EASE)

    def test_grades_match(self):
        grades = re.search(r"const GRADES = \{([^}]+)\}", self.source).group(1)
        parsed = dict(
            (key.strip(), int(value))
            for key, value in (pair.split(":") for pair in grades.split(",") if ":" in pair)
        )
        self.assertEqual(parsed, srs.GRADES)

    def test_generated_files_are_in_sync(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("index.html", "artifact.html"):
            path = os.path.join(root, "mobile", name)
            with open(path, encoding="utf-8") as handle:
                built = handle.read()
            self.assertIn(self.source.strip(), built,
                          f"{name} est périmé : relance revision/mobile/build.py")


class TestAiParsing(unittest.TestCase):
    def test_parse_json_handles_fences_and_prose(self):
        from revision.server import ai
        self.assertEqual(ai.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(ai.parse_json('Voici :\n{"a": {"b": [1, 2]}}\nVoilà.'), {"a": {"b": [1, 2]}})
        with self.assertRaises(ai.AIError):
            ai.parse_json("aucun json ici")

    def test_offline_material_shapes(self):
        from revision.server import ai
        material = ai.offline_material(COURSE, n_flashcards=8, n_qcm=4)
        self.assertTrue(material["flashcards"])
        self.assertLessEqual(len(material["flashcards"]), 8)
        for qcm in material["qcm"]:
            self.assertEqual(len(qcm["choix"]), 4)
            self.assertEqual(qcm["correct"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
