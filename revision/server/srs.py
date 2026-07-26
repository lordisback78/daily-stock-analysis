"""Répétition espacée (SM-2) avec étapes d'apprentissage.

Les notes suivent les 4 boutons de l'interface :
    again (0) / hard (3) / good (4) / easy (5)  -> qualité SM-2
"""
from datetime import datetime, timedelta, timezone

GRADES = {"again": 0, "hard": 3, "good": 4, "easy": 5}

# Étapes d'apprentissage (en minutes) avant de passer en révision espacée.
LEARNING_STEPS = [1, 10]

MIN_EASE = 1.3
DEFAULT_EASE = 2.5


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.replace(microsecond=0).isoformat()


def parse(value):
    if not value:
        return now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return now()


def new_srs():
    return {
        "ease": DEFAULT_EASE,
        "interval": 0,          # en jours (0 = encore en apprentissage)
        "reps": 0,
        "lapses": 0,
        "step": 0,             # position dans LEARNING_STEPS
        "state": "new",        # new | learning | review
        "due": iso(now()),
        "last_review": None,
    }


def is_due(srs, at=None):
    return parse(srs.get("due")) <= (at or now())


def update_ease(ease, quality):
    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return max(MIN_EASE, round(ease, 3))


def review(srs, grade, at=None):
    """Renvoie un nouveau dict SRS après une réponse. Ne mute pas l'entrée."""
    at = at or now()
    srs = {**new_srs(), **(srs or {})}
    quality = GRADES.get(grade, grade if isinstance(grade, int) else 4)
    quality = max(0, min(5, quality))

    if srs["state"] in ("new", "learning"):
        if quality < 3:
            srs["step"] = 0
            if srs["state"] == "learning":
                srs["lapses"] += 1
            srs["state"] = "learning"
            srs["due"] = iso(at + timedelta(minutes=LEARNING_STEPS[0]))
        else:
            step = srs["step"] + (2 if quality == 5 else 1)
            if step >= len(LEARNING_STEPS):
                # Diplômée : passe en révision espacée.
                srs["state"] = "review"
                srs["reps"] = 1
                srs["interval"] = 4 if quality == 5 else 1
                srs["ease"] = update_ease(srs["ease"], quality)
                srs["due"] = iso(at + timedelta(days=srs["interval"]))
            else:
                srs["state"] = "learning"
                srs["step"] = step
                srs["due"] = iso(at + timedelta(minutes=LEARNING_STEPS[step]))
    else:
        if quality < 3:
            srs["lapses"] += 1
            srs["reps"] = 0
            srs["step"] = 0
            srs["state"] = "learning"
            srs["ease"] = update_ease(srs["ease"], quality)
            srs["interval"] = 0
            srs["due"] = iso(at + timedelta(minutes=LEARNING_STEPS[0]))
        else:
            srs["ease"] = update_ease(srs["ease"], quality)
            if srs["reps"] == 0:
                interval = 1
            elif srs["reps"] == 1:
                interval = 6
            else:
                interval = max(1, round(srs["interval"] * srs["ease"]))
            if quality == 3:
                interval = max(1, round(interval * 0.8))
            elif quality == 5:
                interval = round(interval * 1.15)
            srs["reps"] += 1
            srs["interval"] = min(interval, 365 * 2)
            srs["due"] = iso(at + timedelta(days=srs["interval"]))

    srs["last_review"] = iso(at)
    return srs


def maturity(srs):
    interval = (srs or {}).get("interval", 0)
    state = (srs or {}).get("state", "new")
    if state == "new":
        return "nouvelle"
    if state == "learning":
        return "apprentissage"
    if interval < 21:
        return "jeune"
    return "mature"


def preview_intervals(srs):
    """Aperçu des délais pour les 4 boutons (utilisé par l'UI)."""
    out = {}
    base = now()
    for grade in GRADES:
        nxt = review(srs, grade, at=base)
        delta = parse(nxt["due"]) - base
        minutes = delta.total_seconds() / 60
        if minutes < 60:
            label = f"{max(1, round(minutes))} min"
        elif minutes < 60 * 24:
            label = f"{round(minutes / 60)} h"
        elif minutes < 60 * 24 * 30:
            label = f"{round(minutes / 1440)} j"
        else:
            label = f"{round(minutes / 43800)} mois"
        out[grade] = label
    return out
