"""Appels à l'API Claude (stdlib only) + génération de secours hors-ligne."""
import base64
import json
import os
import re
import ssl
import urllib.error
import urllib.request

BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
API_URL = f"{BASE_URL}/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"
MAX_COURSE_CHARS = 120_000


class AIError(RuntimeError):
    pass


def api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def available():
    return bool(api_key())


def _ssl_context():
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        path = os.environ.get(var)
        if path and os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    bundle = "/root/.ccr/ca-bundle.crt"
    if os.path.exists(bundle):
        return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


def call(messages, model=None, max_tokens=8000, system=None, temperature=0.3):
    key = api_key()
    if not key:
        raise AIError("Clé ANTHROPIC_API_KEY absente : ajoute-la dans ton environnement "
                      "ou saisis le contenu du cours à la main.")
    payload = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        payload["system"] = system

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": API_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300, context=_ssl_context()) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise AIError(f"API Claude {exc.code} : {detail}") from exc
    except urllib.error.URLError as exc:
        raise AIError(f"Réseau indisponible : {exc.reason}") from exc

    parts = [block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"]
    return "\n".join(parts).strip()


def parse_json(text):
    """Extrait le premier objet JSON d'une réponse (tolère les ``` et le bavardage)."""
    if not text:
        raise AIError("Réponse vide de Claude")
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth, in_string, escape = 0, False, False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
            elif char == '"':
                in_string = not in_string
            elif not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start:index + 1])
                        except json.JSONDecodeError:
                            break
        start = cleaned.find("{", start + 1)
    raise AIError("Claude n'a pas renvoyé de JSON exploitable")


# --------------------------------------------------------------------------- #
# Transcription de documents (PDF / images)
# --------------------------------------------------------------------------- #

TRANSCRIBE_SYSTEM = (
    "Tu transcris des supports de cours en Markdown propre et fidèle. "
    "Tu conserves la structure (titres, listes, formules, tableaux), tu corriges "
    "les coupures de mots dues à l'OCR, et tu n'ajoutes aucun commentaire."
)


def transcribe(file_bytes, media_type, model=None):
    encoded = base64.b64encode(file_bytes).decode("ascii")
    if media_type == "application/pdf":
        document = {"type": "document", "source": {"type": "base64", "media_type": media_type, "data": encoded}}
    else:
        document = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": encoded}}
    content = [
        document,
        {"type": "text", "text": "Transcris intégralement ce support de cours en Markdown structuré."},
    ]
    return call([{"role": "user", "content": content}], model=model,
                system=TRANSCRIBE_SYSTEM, max_tokens=16000, temperature=0)


# --------------------------------------------------------------------------- #
# Génération du matériel de révision
# --------------------------------------------------------------------------- #

GEN_SYSTEM = """Tu es un professeur agrégé qui prépare du matériel de révision pour un étudiant francophone.
Règles absolues :
- Tu ne t'appuies QUE sur le cours fourni, jamais sur des connaissances extérieures non présentes.
- Chaque question doit être auto-portante (compréhensible sans relire le cours).
- Tu vises la compréhension et la restitution, pas le par-cœur de détails anecdotiques.
- Tu réponds UNIQUEMENT par un objet JSON valide, sans texte autour, sans balises Markdown."""

SCHEMA = """{
  "titre": "titre court du cours",
  "matiere": "matière devinée",
  "fiche": {
    "resume": "5 à 10 phrases de synthèse",
    "plan": [{"titre": "...", "contenu": "2-4 phrases"}],
    "points_cles": ["...", "..."],
    "definitions": [{"terme": "...", "definition": "..."}],
    "pieges": ["erreurs classiques à éviter"]
  },
  "flashcards": [{"question": "...", "reponse": "...", "tag": "sous-thème"}],
  "qcm": [{"question": "...", "choix": ["A", "B", "C", "D"], "correct": 0, "explication": "pourquoi"}],
  "mindmap": {"racine": "...", "branches": [{"titre": "...", "enfants": [{"titre": "...", "enfants": []}]}]}
}"""


def _course_blocks(course_text, cache=True):
    text = course_text[:MAX_COURSE_CHARS]
    block = {"type": "text", "text": f"<cours>\n{text}\n</cours>"}
    if cache and len(text) > 4000:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def generate_material(course_text, n_flashcards=15, n_qcm=10, level="normal",
                      focus=None, model=None):
    consignes = {
        "facile": "Niveau accessible : définitions, notions de base, repères.",
        "normal": "Niveau attendu à un contrôle standard : compréhension et application.",
        "difficile": "Niveau exigeant : raisonnement, liens entre notions, cas limites, pièges d'examen.",
    }.get(level, "")
    focus_line = f"\nConcentre-toi en priorité sur : {focus}." if focus else ""
    prompt = (
        f"Génère le matériel de révision de ce cours.\n"
        f"- {n_flashcards} flashcards (question courte / réponse précise en 1-3 phrases)\n"
        f"- {n_qcm} questions à choix multiples avec 4 propositions et une seule bonne réponse\n"
        f"- une fiche de révision et une mind map hiérarchique (2 niveaux max sous la racine)\n"
        f"{consignes}{focus_line}\n\n"
        f"Format de sortie EXACT :\n{SCHEMA}"
    )
    text = call(
        [{"role": "user", "content": [_course_blocks(course_text), {"type": "text", "text": prompt}]}],
        model=model, system=GEN_SYSTEM, max_tokens=16000, temperature=0.4,
    )
    return parse_json(text)


def answer_question(course_text, question, history=None, model=None):
    """Mode tuteur : pose une question sur son cours."""
    system = ("Tu es un tuteur patient. Tu réponds en français, de façon structurée et concise, "
              "en t'appuyant sur le cours fourni. Si l'information n'y figure pas, tu le dis "
              "explicitement avant de compléter avec tes connaissances générales.")
    messages = [{"role": "user", "content": [_course_blocks(course_text),
                                             {"type": "text", "text": "Voici mon cours, garde-le en mémoire."}]},
                {"role": "assistant", "content": "Cours enregistré, pose-moi tes questions."}]
    for turn in (history or [])[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"][:4000]})
    messages.append({"role": "user", "content": question})
    return call(messages, model=model, system=system, max_tokens=2000, temperature=0.3)


GRADE_SCHEMA = '{"note": 0-100, "verdict": "juste|partiel|faux", "commentaire": "...", "manquants": ["..."]}'


def grade_answer(question, expected, given, model=None):
    prompt = (
        f"Corrige la réponse d'un étudiant, avec bienveillance mais rigueur.\n\n"
        f"Question : {question}\nRéponse attendue : {expected}\nRéponse de l'étudiant : {given}\n\n"
        f"Réponds UNIQUEMENT en JSON : {GRADE_SCHEMA}"
    )
    text = call([{"role": "user", "content": prompt}], model=model,
                system="Tu es un correcteur d'examen français. JSON uniquement.",
                max_tokens=800, temperature=0)
    return parse_json(text)


# --------------------------------------------------------------------------- #
# Secours hors-ligne (sans clé API) : extraction heuristique
# --------------------------------------------------------------------------- #

DEF_PATTERNS = [
    re.compile(r"^\s*(?:[-*•]\s*)?(?P<terme>[A-ZÀ-Ÿ][^:\n]{2,60})\s*:\s*(?P<def>.{20,400})$"),
    re.compile(r"^\s*(?P<terme>[A-ZÀ-Ÿ][^\n]{2,60})\s+(?:est|sont|désigne|correspond à|signifie)\s+(?P<def>.{20,400})$"),
]


def offline_material(course_text, n_flashcards=15, n_qcm=10):
    """Génère un matériel minimal sans IA : définitions repérées + QCM par substitution."""
    lines = [ln.strip() for ln in course_text.splitlines()]
    cards, seen = [], set()
    for line in lines:
        for pattern in DEF_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            terme = match.group("terme").strip(" -•*#").strip()
            definition = match.group("def").strip()
            key = terme.lower()
            if len(terme) < 3 or key in seen:
                continue
            seen.add(key)
            cards.append({"question": f"Que signifie « {terme} » ?", "reponse": definition, "tag": "définitions"})
            break
        if len(cards) >= n_flashcards:
            break

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", course_text) if len(p.strip()) > 120]
    for para in paragraphs:
        if len(cards) >= n_flashcards:
            break
        first = re.split(r"(?<=[.!?])\s", para.strip())[0]
        if len(first) > 30:
            cards.append({"question": f"Développe : {first[:120]}…", "reponse": para[:600], "tag": "compréhension"})

    qcm = []
    for card in cards[:n_qcm]:
        distractors = [c["reponse"][:120] for c in cards if c is not card][:3]
        if len(distractors) < 3:
            break
        choices = [card["reponse"][:120]] + distractors
        qcm.append({"question": card["question"], "choix": choices, "correct": 0,
                    "explication": "Réponse issue du cours (généré hors-ligne, sans IA)."})

    heading = next((ln.strip("# ").strip() for ln in lines if ln.strip()), "Cours")
    key_points = [ln.strip(" -•*") for ln in lines if re.match(r"^\s*[-*•]\s+\S", ln)][:10]
    return {
        "titre": heading[:80],
        "matiere": "",
        "fiche": {
            "resume": " ".join(re.split(r"(?<=[.!?])\s", course_text.strip())[:6])[:1200],
            "plan": [{"titre": ln.strip("# ").strip(), "contenu": ""} for ln in lines if ln.startswith("#")][:12],
            "points_cles": key_points,
            "definitions": [{"terme": c["question"][14:-4], "definition": c["reponse"]}
                            for c in cards if c["tag"] == "définitions"][:12],
            "pieges": [],
        },
        "flashcards": cards[:n_flashcards],
        "qcm": qcm,
        "mindmap": {"racine": heading[:60],
                    "branches": [{"titre": ln.strip("# ").strip(), "enfants": []}
                                 for ln in lines if ln.startswith("#")][:8]},
        "offline": True,
    }
