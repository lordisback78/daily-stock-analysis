"""Persistance JSON simple (mono-utilisateur, écriture atomique)."""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("REVISION_DATA_DIR", os.path.join(BASE_DIR, "data"))
STORE_PATH = os.path.join(DATA_DIR, "store.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

DEFAULT_SETTINGS = {
    "model": "claude-sonnet-5",
    "daily_goal": 30,
    "flashcards_per_generation": 15,
    "qcm_per_generation": 10,
    "theme": "auto",
}

_lock = threading.RLock()
_cache = None


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty():
    return {"version": 1, "courses": [], "cards": [], "reviews": [], "settings": dict(DEFAULT_SETTINGS)}


def load():
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        if os.path.exists(STORE_PATH):
            try:
                with open(STORE_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                backup = STORE_PATH + ".corrupt"
                try:
                    os.replace(STORE_PATH, backup)
                    print(f"⚠️ store.json illisible, sauvegardé dans {backup}")
                except OSError:
                    pass
                data = _empty()
        else:
            data = _empty()
        base = _empty()
        base.update(data)
        base["settings"] = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
        _cache = base
        return _cache


def save():
    with _lock:
        data = load()
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STORE_PATH)


class transaction:
    """`with transaction() as db:` -> écrit le store à la sortie."""

    def __enter__(self):
        _lock.acquire()
        return load()

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                save()
        finally:
            _lock.release()
        return False


def find(collection, item_id):
    for item in load()[collection]:
        if item["id"] == item_id:
            return item
    return None


def cards_of(course_id):
    return [c for c in load()["cards"] if c["course_id"] == course_id]


def upload_path(course_id, filename):
    ext = os.path.splitext(filename)[1].lower()[:8]
    safe = "".join(ch for ch in ext if ch.isalnum() or ch == ".")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return os.path.join(UPLOAD_DIR, f"{course_id}{safe}")
