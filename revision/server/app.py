"""Serveur HTTP de l'application de révision (stdlib uniquement)."""
import base64
import json
import mimetypes
import os
import random
import re
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import ai, extract, srs, store

WEB_DIR = os.path.join(store.BASE_DIR, "web")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------- #
# Helpers métier
# --------------------------------------------------------------------------- #

def today_local():
    return datetime.now().date()


def due_cards(db, course_id=None, at=None):
    at = at or srs.now()
    cards = db["cards"]
    if course_id:
        cards = [c for c in cards if c["course_id"] == course_id]
    return [c for c in cards if srs.is_due(c["srs"], at)]


def course_summary(db, course):
    cards = [c for c in db["cards"] if c["course_id"] == course["id"]]
    due = [c for c in cards if srs.is_due(c["srs"])]
    mature = [c for c in cards if srs.maturity(c["srs"]) == "mature"]
    new = [c for c in cards if c["srs"]["state"] == "new"]
    progress = round(100 * len(mature) / len(cards)) if cards else 0
    return {
        "id": course["id"],
        "title": course["title"],
        "subject": course.get("subject") or "",
        "kind": course.get("kind", "txt"),
        "created_at": course["created_at"],
        "chars": len(course.get("text") or ""),
        "has_material": bool(course.get("fiche")),
        "exam_date": course.get("exam_date") or "",
        "counts": {
            "cards": len(cards),
            "flashcards": sum(1 for c in cards if c["type"] == "flashcard"),
            "qcm": sum(1 for c in cards if c["type"] == "qcm"),
            "due": len(due),
            "new": len(new),
            "mature": len(mature),
        },
        "progress": progress,
    }


def reviews_by_day(db, days=120):
    counter = Counter()
    for review in db["reviews"]:
        counter[review["ts"][:10]] += 1
    out = []
    start = today_local() - timedelta(days=days - 1)
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        out.append({"date": day, "count": counter.get(day, 0)})
    return out


def streak(db):
    days = {review["ts"][:10] for review in db["reviews"]}
    if not days:
        return 0
    count, cursor = 0, today_local()
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
        if cursor.isoformat() not in days:
            return 0
    while cursor.isoformat() in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def missions(db):
    goal = db["settings"].get("daily_goal", 30)
    today = today_local().isoformat()
    done_today = sum(1 for r in db["reviews"] if r["ts"][:10] == today)
    due = len(due_cards(db))
    out = [{
        "id": "daily",
        "label": f"Réviser {goal} cartes",
        "done": min(done_today, goal),
        "total": goal,
        "action": "review",
    }]
    if due:
        out.append({
            "id": "clear_due",
            "label": f"Vider la file du jour ({due} carte{'s' if due > 1 else ''})",
            "done": 0 if due else 1,
            "total": 1,
            "action": "review",
        })
    # Cours généré mais jamais révisé
    for course in db["courses"]:
        cards = [c for c in db["cards"] if c["course_id"] == course["id"]]
        if cards and all(c["srs"]["state"] == "new" for c in cards):
            out.append({
                "id": f"start_{course['id']}",
                "label": f"Démarrer « {course['title'][:40]} »",
                "done": 0, "total": 1, "action": "review", "course_id": course["id"],
            })
            break
    # Cours sans matériel
    for course in db["courses"]:
        if not [c for c in db["cards"] if c["course_id"] == course["id"]]:
            out.append({
                "id": f"gen_{course['id']}",
                "label": f"Générer les cartes de « {course['title'][:40]} »",
                "done": 0, "total": 1, "action": "generate", "course_id": course["id"],
            })
            break
    # Examen proche
    for course in db["courses"]:
        if course.get("exam_date"):
            try:
                left = (datetime.fromisoformat(course["exam_date"]).date() - today_local()).days
            except ValueError:
                continue
            if 0 <= left <= 14:
                out.append({
                    "id": f"exam_{course['id']}",
                    "label": f"Examen « {course['title'][:30]} » dans {left} j → blanc d'entraînement",
                    "done": 0, "total": 1, "action": "exam", "course_id": course["id"],
                })
    return out


def stats(db):
    cards = db["cards"]
    grades = Counter(r["grade"] for r in db["reviews"])
    total = sum(grades.values())
    correct = grades["good"] + grades["easy"]
    per_subject = {}
    for course in db["courses"]:
        subject = course.get("subject") or "Sans matière"
        bucket = per_subject.setdefault(subject, {"cards": 0, "mature": 0, "due": 0})
        for card in cards:
            if card["course_id"] != course["id"]:
                continue
            bucket["cards"] += 1
            if srs.maturity(card["srs"]) == "mature":
                bucket["mature"] += 1
            if srs.is_due(card["srs"]):
                bucket["due"] += 1
    return {
        "cards": len(cards),
        "courses": len(db["courses"]),
        "reviews": total,
        "accuracy": round(100 * correct / total) if total else 0,
        "maturity": dict(Counter(srs.maturity(c["srs"]) for c in cards)),
        "grades": dict(grades),
        "streak": streak(db),
        "heatmap": reviews_by_day(db),
        "per_subject": per_subject,
        "forecast": forecast(db),
    }


def forecast(db, days=14):
    counter = Counter()
    now = srs.now()
    for card in db["cards"]:
        due = srs.parse(card["srs"]["due"])
        offset = (due.date() - now.date()).days
        counter[max(0, min(offset, days))] += 1
    return [{"day": offset, "count": counter.get(offset, 0)} for offset in range(days + 1)]


def make_card(course_id, card_type, payload):
    card = {
        "id": store.new_id("card"),
        "course_id": course_id,
        "type": card_type,
        "question": (payload.get("question") or "").strip(),
        "answer": (payload.get("reponse") or payload.get("answer") or "").strip(),
        "tag": (payload.get("tag") or "").strip(),
        "created_at": store.now_iso(),
        "srs": srs.new_srs(),
        "suspended": False,
    }
    if card_type == "qcm":
        choices = [str(c).strip() for c in (payload.get("choix") or payload.get("choices") or []) if str(c).strip()]
        correct = payload.get("correct", 0)
        try:
            correct = int(correct)
        except (TypeError, ValueError):
            correct = 0
        if not 0 <= correct < len(choices):
            correct = 0
        card["choices"] = choices
        card["correct"] = correct
        card["explanation"] = (payload.get("explication") or payload.get("explanation") or "").strip()
        card["answer"] = choices[correct] if choices else card["answer"]
    return card


def store_material(db, course, material):
    """Enregistre fiche/mindmap sur le cours et crée les cartes (sans doublons)."""
    fiche = material.get("fiche") or {}
    if fiche:
        course["fiche"] = fiche
    if material.get("mindmap"):
        course["mindmap"] = material["mindmap"]
    if material.get("matiere") and not course.get("subject"):
        course["subject"] = material["matiere"]

    def dedup_key(question, card_type):
        return re.sub(r"\W+", "", (question or "").lower()) + ("|qcm" if card_type == "qcm" else "")

    existing = {dedup_key(c["question"], c["type"]) for c in db["cards"] if c["course_id"] == course["id"]}
    created = 0
    for payload in material.get("flashcards") or []:
        question = (payload.get("question") or "").strip()
        answer = (payload.get("reponse") or payload.get("answer") or "").strip()
        if not question or not answer:
            continue
        key = dedup_key(question, "flashcard")
        if key in existing:
            continue
        existing.add(key)
        db["cards"].append(make_card(course["id"], "flashcard", payload))
        created += 1
    for payload in material.get("qcm") or []:
        question = (payload.get("question") or "").strip()
        choices = payload.get("choix") or payload.get("choices") or []
        if not question or len(choices) < 2:
            continue
        key = dedup_key(question, "qcm")
        if key in existing:
            continue
        existing.add(key)
        db["cards"].append(make_card(course["id"], "qcm", payload))
        created += 1
    course["generated_at"] = store.now_iso()
    return created


def public_card(card, with_answer=True):
    out = {
        "id": card["id"],
        "course_id": card["course_id"],
        "type": card["type"],
        "question": card["question"],
        "tag": card.get("tag", ""),
        "srs": card["srs"],
        "maturity": srs.maturity(card["srs"]),
        "intervals": srs.preview_intervals(card["srs"]),
    }
    if card["type"] == "qcm":
        out["choices"] = card.get("choices", [])
    if with_answer:
        out["answer"] = card.get("answer", "")
        out["explanation"] = card.get("explanation", "")
        if card["type"] == "qcm":
            out["correct"] = card.get("correct", 0)
    return out


# --------------------------------------------------------------------------- #
# Routes API
# --------------------------------------------------------------------------- #

def api_state(_query, _body):
    db = store.load()
    return {
        "courses": [course_summary(db, c) for c in db["courses"]],
        "settings": db["settings"],
        "missions": missions(db),
        "due": len(due_cards(db)),
        "streak": streak(db),
        "ai_available": ai.available(),
        "model": db["settings"].get("model", ai.DEFAULT_MODEL),
    }


def api_stats(_query, _body):
    return stats(store.load())


def api_settings_put(_query, body):
    with store.transaction() as db:
        for key in store.DEFAULT_SETTINGS:
            if key in body:
                db["settings"][key] = body[key]
        return db["settings"]


def api_course_create(_query, body):
    title = (body.get("title") or "").strip()
    subject = (body.get("subject") or "").strip()
    text = body.get("text") or ""
    filename = body.get("filename") or ""
    data_b64 = body.get("data_b64") or ""
    kind = "txt"
    media_type = None
    needs_ai = False
    raw = b""

    if data_b64:
        try:
            raw = base64.b64decode(data_b64, validate=True)
        except Exception as exc:
            raise ApiError(f"Fichier illisible : {exc}")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ApiError("Fichier trop volumineux (25 Mo max)")
        result = extract.extract(filename, raw)
        if result.get("error"):
            raise ApiError(result["error"])
        text, needs_ai, kind, media_type = result["text"], result["needs_ai"], result["kind"], result["media_type"]

    course_id = store.new_id("course")
    transcribed = False
    partial = False
    if needs_ai and raw and media_type:
        if ai.available():
            text = ai.transcribe(raw, media_type, model=store.load()["settings"].get("model"))
            transcribed = True
        elif (text or "").strip():
            partial = True  # extraction locale imparfaite mais exploitable
        else:
            raise ApiError(
                "Ce document n'est pas lisible sans IA (PDF scanné ou image). "
                "Ajoute ANTHROPIC_API_KEY, ou colle le texte du cours directement.", 422)

    if not (text or "").strip():
        raise ApiError("Aucun contenu de cours détecté")

    with store.transaction() as db:
        if raw:
            try:
                with open(store.upload_path(course_id, filename), "wb") as handle:
                    handle.write(raw)
            except OSError:
                pass
        course = {
            "id": course_id,
            "title": title or (os.path.splitext(filename)[0] if filename else text.strip().splitlines()[0][:60]) or "Cours",
            "subject": subject,
            "kind": kind,
            "source_file": filename,
            "text": text.strip(),
            "created_at": store.now_iso(),
            "exam_date": (body.get("exam_date") or "").strip(),
            "fiche": None,
            "mindmap": None,
        }
        db["courses"].insert(0, course)
        return {"course": course_summary(db, course), "transcribed": transcribed, "partial": partial}


def api_course_get(course_id, _query, _body):
    db = store.load()
    course = store.find("courses", course_id)
    if not course:
        raise ApiError("Cours introuvable", 404)
    cards = [public_card(c) for c in db["cards"] if c["course_id"] == course_id]
    return {
        "course": {**course_summary(db, course), "text": course.get("text", ""),
                   "fiche": course.get("fiche"), "mindmap": course.get("mindmap")},
        "cards": cards,
    }


def api_course_patch(course_id, _query, body):
    with store.transaction() as db:
        course = next((c for c in db["courses"] if c["id"] == course_id), None)
        if not course:
            raise ApiError("Cours introuvable", 404)
        for field in ("title", "subject", "text", "exam_date"):
            if field in body:
                course[field] = (body[field] or "").strip()
        return course_summary(db, course)


def api_course_delete(course_id, _query, _body):
    with store.transaction() as db:
        before = len(db["courses"])
        db["courses"] = [c for c in db["courses"] if c["id"] != course_id]
        if len(db["courses"]) == before:
            raise ApiError("Cours introuvable", 404)
        removed = [c["id"] for c in db["cards"] if c["course_id"] == course_id]
        db["cards"] = [c for c in db["cards"] if c["course_id"] != course_id]
        db["reviews"] = [r for r in db["reviews"] if r["card_id"] not in removed]
        for name in os.listdir(store.UPLOAD_DIR) if os.path.isdir(store.UPLOAD_DIR) else []:
            if name.startswith(course_id):
                try:
                    os.remove(os.path.join(store.UPLOAD_DIR, name))
                except OSError:
                    pass
        return {"deleted": course_id, "cards_removed": len(removed)}


def api_course_generate(course_id, _query, body):
    course = store.find("courses", course_id)
    if not course:
        raise ApiError("Cours introuvable", 404)
    settings = store.load()["settings"]
    n_flashcards = int(body.get("n_flashcards") or settings.get("flashcards_per_generation", 15))
    n_qcm = int(body.get("n_qcm") or settings.get("qcm_per_generation", 10))
    level = body.get("level") or "normal"
    focus = (body.get("focus") or "").strip() or None

    if ai.available():
        material = ai.generate_material(course["text"], n_flashcards=n_flashcards, n_qcm=n_qcm,
                                        level=level, focus=focus, model=settings.get("model"))
    else:
        material = ai.offline_material(course["text"], n_flashcards=n_flashcards, n_qcm=n_qcm)

    with store.transaction() as db:
        stored = next(c for c in db["courses"] if c["id"] == course_id)
        created = store_material(db, stored, material)
        return {"created": created, "offline": bool(material.get("offline")),
                "course": course_summary(db, stored),
                "fiche": stored.get("fiche"), "mindmap": stored.get("mindmap")}


def api_course_ask(course_id, _query, body):
    course = store.find("courses", course_id)
    if not course:
        raise ApiError("Cours introuvable", 404)
    question = (body.get("question") or "").strip()
    if not question:
        raise ApiError("Question vide")
    if not ai.available():
        raise ApiError("Le mode tuteur nécessite ANTHROPIC_API_KEY", 422)
    answer = ai.answer_question(course["text"], question, history=body.get("history"),
                               model=store.load()["settings"].get("model"))
    return {"answer": answer}


def api_session(query, _body):
    db = store.load()
    scope = (query.get("scope") or ["due"])[0]
    course_id = (query.get("course_id") or [None])[0]
    limit = int((query.get("limit") or [20])[0])
    card_type = (query.get("type") or [None])[0]

    pool = [c for c in db["cards"] if not c.get("suspended")]
    if course_id:
        pool = [c for c in pool if c["course_id"] == course_id]
    if card_type in ("flashcard", "qcm"):
        pool = [c for c in pool if c["type"] == card_type]

    if scope == "due":
        selection = [c for c in pool if srs.is_due(c["srs"])]
        selection.sort(key=lambda c: (c["srs"]["state"] != "learning", c["srs"]["due"]))
    elif scope == "new":
        selection = [c for c in pool if c["srs"]["state"] == "new"]
    elif scope == "hard":
        selection = sorted(pool, key=lambda c: (-c["srs"].get("lapses", 0), c["srs"].get("ease", 2.5)))
        selection = [c for c in selection if c["srs"].get("lapses", 0) > 0] or selection
    else:  # all / entraînement libre
        selection = list(pool)
        random.shuffle(selection)

    titles = {c["id"]: c["title"] for c in db["courses"]}
    cards = [{**public_card(c), "course_title": titles.get(c["course_id"], "")} for c in selection[:limit]]
    return {"cards": cards, "remaining": max(0, len(selection) - len(cards)), "scope": scope}


def api_review(_query, body):
    card_id = body.get("card_id")
    grade = body.get("grade")
    if grade not in srs.GRADES:
        raise ApiError("Note invalide (again|hard|good|easy)")
    with store.transaction() as db:
        card = next((c for c in db["cards"] if c["id"] == card_id), None)
        if not card:
            raise ApiError("Carte introuvable", 404)
        card["srs"] = srs.review(card["srs"], grade)
        db["reviews"].append({
            "card_id": card_id,
            "course_id": card["course_id"],
            "ts": store.now_iso(),
            "grade": grade,
            "ms": int(body.get("ms") or 0),
        })
        return {"card": public_card(card), "due": len(due_cards(db)),
                "done_today": sum(1 for r in db["reviews"] if r["ts"][:10] == today_local().isoformat())}


def api_card_create(_query, body):
    course_id = body.get("course_id")
    if not store.find("courses", course_id):
        raise ApiError("Cours introuvable", 404)
    card_type = body.get("type") or "flashcard"
    if card_type not in ("flashcard", "qcm"):
        raise ApiError("Type de carte invalide")
    with store.transaction() as db:
        card = make_card(course_id, card_type, body)
        if not card["question"] or not (card["answer"] or card.get("choices")):
            raise ApiError("Question et réponse obligatoires")
        db["cards"].append(card)
        return public_card(card)


def api_card_patch(card_id, _query, body):
    with store.transaction() as db:
        card = next((c for c in db["cards"] if c["id"] == card_id), None)
        if not card:
            raise ApiError("Carte introuvable", 404)
        for field in ("question", "answer", "tag", "explanation"):
            if field in body:
                card[field] = (body[field] or "").strip()
        if "choices" in body:
            card["choices"] = [str(c).strip() for c in body["choices"] if str(c).strip()]
        if "correct" in body and card["type"] == "qcm":
            card["correct"] = max(0, min(int(body["correct"]), len(card.get("choices", [1])) - 1))
            if card.get("choices"):
                card["answer"] = card["choices"][card["correct"]]
        if "suspended" in body:
            card["suspended"] = bool(body["suspended"])
        if body.get("reset"):
            card["srs"] = srs.new_srs()
        return public_card(card)


def api_card_delete(card_id, _query, _body):
    with store.transaction() as db:
        before = len(db["cards"])
        db["cards"] = [c for c in db["cards"] if c["id"] != card_id]
        if len(db["cards"]) == before:
            raise ApiError("Carte introuvable", 404)
        db["reviews"] = [r for r in db["reviews"] if r["card_id"] != card_id]
        return {"deleted": card_id}


def api_exam(_query, body):
    db = store.load()
    course_id = body.get("course_id")
    count = max(3, min(int(body.get("count") or 15), 60))
    pool = [c for c in db["cards"] if not c.get("suspended")]
    if course_id and course_id != "all":
        pool = [c for c in pool if c["course_id"] == course_id]
    if not pool:
        raise ApiError("Aucune carte disponible pour composer l'examen", 422)

    qcm = [c for c in pool if c["type"] == "qcm"]
    flash = [c for c in pool if c["type"] == "flashcard"]
    random.shuffle(qcm)
    random.shuffle(flash)
    half = count // 2
    chosen = qcm[:max(half, count - len(flash))] + flash[:count - len(qcm[:max(half, count - len(flash))])]
    random.shuffle(chosen)
    titles = {c["id"]: c["title"] for c in db["courses"]}
    questions = []
    for card in chosen[:count]:
        item = {"id": card["id"], "type": card["type"], "question": card["question"],
                "course_title": titles.get(card["course_id"], ""), "tag": card.get("tag", "")}
        if card["type"] == "qcm":
            order = list(range(len(card.get("choices", []))))
            random.shuffle(order)
            item["choices"] = [card["choices"][i] for i in order]
            item["correct"] = order.index(card.get("correct", 0))
        else:
            item["answer"] = card.get("answer", "")
        questions.append(item)
    return {"questions": questions, "ai_grading": ai.available()}


def api_grade(_query, body):
    if not ai.available():
        raise ApiError("La correction automatique nécessite ANTHROPIC_API_KEY", 422)
    question = (body.get("question") or "").strip()
    expected = (body.get("expected") or "").strip()
    given = (body.get("given") or "").strip()
    if not (question and expected):
        raise ApiError("Question et réponse attendue obligatoires")
    if not given:
        return {"note": 0, "verdict": "faux", "commentaire": "Aucune réponse fournie.", "manquants": []}
    return ai.grade_answer(question, expected, given, model=store.load()["settings"].get("model"))


def api_export(_query, _body):
    db = store.load()
    return {"exported_at": store.now_iso(), "courses": db["courses"], "cards": db["cards"],
            "reviews": db["reviews"], "settings": db["settings"]}


ROUTES = {
    ("GET", "/api/state"): api_state,
    ("GET", "/api/stats"): api_stats,
    ("GET", "/api/session"): api_session,
    ("GET", "/api/export"): api_export,
    ("PUT", "/api/settings"): api_settings_put,
    ("POST", "/api/courses"): api_course_create,
    ("POST", "/api/cards"): api_card_create,
    ("POST", "/api/review"): api_review,
    ("POST", "/api/exam"): api_exam,
    ("POST", "/api/grade"): api_grade,
}

PATTERN_ROUTES = [
    ("GET", re.compile(r"^/api/courses/([\w-]+)$"), api_course_get),
    ("PATCH", re.compile(r"^/api/courses/([\w-]+)$"), api_course_patch),
    ("DELETE", re.compile(r"^/api/courses/([\w-]+)$"), api_course_delete),
    ("POST", re.compile(r"^/api/courses/([\w-]+)/generate$"), api_course_generate),
    ("POST", re.compile(r"^/api/courses/([\w-]+)/ask$"), api_course_ask),
    ("PATCH", re.compile(r"^/api/cards/([\w-]+)$"), api_card_patch),
    ("DELETE", re.compile(r"^/api/cards/([\w-]+)$"), api_card_delete),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "OriaLike/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("REVISION_VERBOSE"):
            super().log_message(fmt, *args)

    # -- helpers ---------------------------------------------------------- #
    def _send(self, status, payload=None, body=None, content_type="application/json; charset=utf-8"):
        if body is None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        if length > MAX_UPLOAD_BYTES + 2_000_000:
            raise ApiError("Requête trop volumineuse", 413)
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError("Corps JSON invalide")

    def _serve_static(self, path):
        if path in ("/", "", "/index.html"):
            path = "/index.html"
        target = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not target.startswith(WEB_DIR) or not os.path.isfile(target):
            self._send(404, {"error": "Introuvable"})
            return
        mime = mimetypes.guess_type(target)[0] or "application/octet-stream"
        with open(target, "rb") as handle:
            body = handle.read()
        charset = "; charset=utf-8" if mime.startswith(("text/", "application/javascript")) else ""
        self._send(200, body=body, content_type=mime + charset)

    def _handle(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if not path.startswith("/api/"):
            if self.command in ("GET", "HEAD"):
                self._serve_static(parsed.path)
            else:
                self._send(405, {"error": "Méthode non autorisée"})
            return

        try:
            body = self._read_body() if self.command in ("POST", "PUT", "PATCH") else {}
            handler = ROUTES.get((self.command, path))
            if handler:
                self._send(200, handler(query, body))
                return
            for method, pattern, pattern_handler in PATTERN_ROUTES:
                match = pattern.match(path)
                if match and method == self.command:
                    self._send(200, pattern_handler(match.group(1), query, body))
                    return
            self._send(404, {"error": f"Route inconnue : {self.command} {path}"})
        except ApiError as exc:
            self._send(exc.status, {"error": exc.message})
        except ai.AIError as exc:
            self._send(502, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - garde-fou
            traceback.print_exc()
            self._send(500, {"error": f"Erreur interne : {exc}"})

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = _handle


def serve(host="127.0.0.1", port=8765):
    store.load()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"✅ Révision prête sur http://{host}:{port}")
    print(f"   Données : {store.STORE_PATH}")
    print("   IA : " + ("activée (ANTHROPIC_API_KEY détectée)" if ai.available()
                        else "désactivée — mode hors-ligne (ajoute ANTHROPIC_API_KEY pour la génération)"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Arrêt du serveur")
    finally:
        httpd.server_close()
