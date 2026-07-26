#!/usr/bin/env python3
"""Assemble l'app mobile depuis sa source unique.

    python3 revision/mobile/build.py

Produit :
- index.html    page complète installable (manifest, icônes, service worker)
- artifact.html même app sans <html>/<head>/<body>, pour publication en artefact
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "app.body.html")

PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Révisions</title>
<meta name="description" content="Réviser ses cours : flashcards, QCM et examens en répétition espacée, hors ligne.">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Révisions">
<meta name="theme-color" content="#f4f3fa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f0f18" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="./manifest.webmanifest">
<link rel="apple-touch-icon" href="./icon-180.png">
<link rel="icon" type="image/png" href="./icon-192.png">
</head>
<body>
{body}
</body>
</html>
"""

ARTIFACT = """<title>Révisions</title>
{body}
"""


def main():
    with open(SOURCE, encoding="utf-8") as handle:
        body = handle.read().strip()

    for name, template in (("index.html", PAGE), ("artifact.html", ARTIFACT)):
        path = os.path.join(HERE, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(template.replace("{body}", body))
        print(f"✅ {name} ({os.path.getsize(path) // 1024} Ko)")


if __name__ == "__main__":
    main()
