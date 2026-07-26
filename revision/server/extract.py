"""Extraction de texte depuis les formats de cours courants (stdlib uniquement).

- .txt / .md / .csv / .html : décodage direct
- .docx / .pptx / .odt     : dézippage + nettoyage XML
- .pdf                     : extraction best-effort (flux FlateDecode)
- images                   : pas d'extraction locale -> transmises à Claude (vision)

Quand l'extraction locale est trop pauvre, `needs_ai` vaut True et le fichier
d'origine est envoyé à Claude pour transcription.
"""
import html
import io
import re
import zipfile
import zlib

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".rst", ".org", ".json"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
NATIVE_PDF_EXT = {".pdf"}

IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

MIN_USEFUL_CHARS = 400


def ext_of(filename):
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def _strip_xml(xml_text, para_tags=("</w:p>", "</a:p>", "</text:p>", "</text:h>")):
    for tag in para_tags:
        xml_text = xml_text.replace(tag, "\n")
    xml_text = xml_text.replace("<w:br/>", "\n").replace("<a:br/>", "\n")
    xml_text = re.sub(r"<[^>]+>", "", xml_text)
    text = html.unescape(xml_text)
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _from_zip_xml(data, members):
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        for name in members(names):
            if name in names:
                out.append(_strip_xml(zf.read(name).decode("utf-8", "replace")))
    return "\n\n".join(part for part in out if part)


def from_docx(data):
    def members(_names):
        return ["word/document.xml"]

    return _from_zip_xml(data, members)


def from_pptx(data):
    def members(names):
        slides = [n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        notes = [n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)]

        def order(name):
            return int(re.search(r"(\d+)\.xml$", name).group(1))

        return sorted(slides, key=order) + sorted(notes, key=order)

    return _from_zip_xml(data, members)


def from_odt(data):
    def members(_names):
        return ["content.xml"]

    return _from_zip_xml(data, members)


def _decode_pdf_string(raw):
    out = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            mapping = {"n": "\n", "r": "\n", "t": " ", "b": "", "f": "", "(": "(", ")": ")", "\\": "\\"}
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            if nxt.isdigit():
                octal = raw[i + 1:i + 4]
                digits = ""
                for d in octal:
                    if d.isdigit():
                        digits += d
                    else:
                        break
                try:
                    out.append(chr(int(digits, 8)))
                except ValueError:
                    pass
                i += 1 + len(digits)
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _pdf_text_from_content(content):
    """Récupère le texte des opérateurs Tj / TJ / ' / " d'un flux PDF."""
    pieces = []
    for match in re.finditer(r"\((?:[^()\\]|\\.)*\)|\bT[dDmJj*]\b|\bTD\b|\bET\b", content):
        token = match.group(0)
        if token.startswith("("):
            pieces.append(_decode_pdf_string(token[1:-1]))
        elif token in ("Td", "TD", "T*", "ET"):
            pieces.append("\n")
        else:
            pieces.append(" ")
    text = "".join(pieces)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def from_pdf(data):
    """Extraction best-effort : décompresse les flux et lit les opérateurs texte."""
    chunks = []
    for match in re.finditer(rb"stream\r?\n?(.*?)endstream", data, re.DOTALL):
        raw = match.group(1)
        content = None
        try:
            content = zlib.decompress(raw)
        except zlib.error:
            try:
                content = zlib.decompressobj().decompress(raw)
            except zlib.error:
                if b"BT" in raw and b"(" in raw:
                    content = raw
        if not content:
            continue
        try:
            decoded = content.decode("latin-1", "replace")
        except Exception:  # pragma: no cover - latin-1 ne lève pas
            continue
        if "BT" not in decoded and "Tj" not in decoded and "TJ" not in decoded:
            continue
        text = _pdf_text_from_content(decoded)
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


COMMON_WORDS = re.compile(
    r"\b(le|la|les|des|du|de|et|est|sont|un|une|dans|pour|que|qui|sur|avec|par|aux|ce|cette|plus"
    r"|the|of|and|to|in|is|for)\b", re.IGNORECASE)


def looks_garbled(text):
    """Vrai si le texte n'est pas du langage lisible.

    Deux symptômes distincts : une soupe de symboles (polices exotiques), ou des
    lettres décalées par un encodage de sous-ensemble — celles-ci passent le test
    de jeu de caractères, d'où la recherche de mots courants.
    """
    if not text:
        return True
    sample = text[:6000]
    letters = sum(ch.isalpha() or ch.isspace() or ch in ",.;:!?'\"()-–—%°" for ch in sample)
    if letters / max(1, len(sample)) < 0.75:
        return True
    alphabetic = sum(ch.isalpha() for ch in sample)
    return alphabetic > 300 and len(COMMON_WORDS.findall(sample)) < 3


def extract(filename, data):
    """-> dict(text, needs_ai, kind, media_type)"""
    ext = ext_of(filename)
    kind = ext.lstrip(".") or "txt"

    if ext in IMAGE_EXT:
        return {"text": "", "needs_ai": True, "kind": "image", "media_type": IMAGE_MEDIA[ext]}

    if ext in NATIVE_PDF_EXT:
        text = from_pdf(data)
        weak = len(text) < MIN_USEFUL_CHARS or looks_garbled(text)
        if weak and looks_garbled(text):
            text = ""  # illisible : seule la vision de Claude peut aider
        return {"text": text, "needs_ai": weak, "kind": "pdf", "media_type": "application/pdf"}

    if ext == ".docx":
        text = from_docx(data)
    elif ext == ".pptx":
        text = from_pptx(data)
    elif ext in (".odt", ".odp"):
        text = from_odt(data)
    elif ext in (".html", ".htm"):
        text = _strip_xml(data.decode("utf-8", "replace"), para_tags=("</p>", "</div>", "</li>", "</h1>", "</h2>", "</h3>", "<br/>", "<br>"))
    elif ext in TEXT_EXT or not ext:
        text = data.decode("utf-8", "replace")
    else:
        text = data.decode("utf-8", "replace")
        if looks_garbled(text):
            return {"text": "", "needs_ai": False, "kind": kind, "media_type": None,
                    "error": f"Format {ext or '?'} non pris en charge"}

    return {"text": text.strip(), "needs_ai": len(text.strip()) < 40, "kind": kind, "media_type": None}
