# 📱 Révisions — version installable (iPhone / iPad / Android)

Même app que la version desktop, mais **entièrement dans le navigateur** : aucun
serveur à lancer, données dans le stockage local de l'appareil, fonctionne en
avion. C'est cette version qu'on installe sur l'écran d'accueil.

## Installer sur l'écran d'accueil de l'iPhone

1. Ouvre l'app dans **Safari** (voir les deux hébergements ci-dessous).
2. Bouton **Partager** (carré avec flèche) → **Sur l'écran d'accueil**.
3. L'icône « Révisions » apparaît ; l'app s'ouvre en plein écran, sans barre
   d'adresse, et garde ses données entre les lancements.

> Safari est obligatoire pour cette étape : Chrome iOS ne propose pas
> « Sur l'écran d'accueil ».

### Hébergement A — l'artefact claude.ai (le plus rapide)

Rien à configurer, lien privé, prêt à installer. Limite : la page hébergée
bloque les appels réseau sortants, donc **pas de génération par Claude** — les
cartes sont fabriquées sur l'appareil, ou importées depuis la version desktop.

### Hébergement B — GitHub Pages (le plus complet)

Sert `revision/mobile/` comme un vrai site : service worker (démarrage hors
ligne), icône, mode plein écran, et génération par Claude possible avec ta
propre clé API.

1. Dépôt → **Settings → Pages**
2. *Source* : **Deploy from a branch** ; branche `main` (ou la branche de
   travail), dossier `/ (root)`
3. Attends le déploiement, puis ouvre
   `https://<ton-compte>.github.io/daily-stock-analysis/revision/mobile/`
4. Installe depuis Safari comme ci-dessus.

Le dépôt doit être public (ou GitHub Pages activé sur un plan payant).

### Hébergement C — depuis ton Mac, sur le Wi-Fi de la maison

```bash
python3 -m http.server 8000 --directory revision/mobile --bind 0.0.0.0
```

Puis, sur l'iPhone : `http://<ip-du-mac>:8000/`. Pratique pour tester, mais le
Mac doit rester allumé et iOS n'accorde pas le mode hors-ligne complet sur une
origine non sécurisée.

## Alimenter les cartes : trois chemins

| Chemin | Qualité | Où |
| --- | --- | --- |
| **Fabrication sur l'appareil** | correcte sur un cours bien structuré (repère les `Terme : définition`) | partout, sans clé |
| **Import d'un deck JSON** | celle de Claude | export depuis la version desktop → *Cours → Importer un deck* |
| **Clé API dans Réglages** | celle de Claude | hébergement B ou C uniquement |

Le pont recommandé : les cours arrivent sur l'ordinateur, `python3 revision/run.py`
génère le matériel avec Claude, **Réglages → Exporter** produit un JSON que tu
ouvres sur le téléphone (AirDrop, Fichiers, iCloud) via *Importer un deck*.
L'historique de révision est fusionné, pas écrasé.

À propos de la clé API : elle est stockée dans le `localStorage` de l'appareil,
n'est jamais incluse dans les exports, et ne part que vers `api.anthropic.com`.
Sur un téléphone partagé, préfère l'import de deck.

## Formats de fichiers lus dans le navigateur

| Format | Méthode |
| --- | --- |
| `.txt` `.md` `.csv` `.html` | lecture directe |
| `.docx` `.pptx` `.odt` | ZIP dézippé via `DecompressionStream`, texte extrait du XML |
| `.pdf` | flux `FlateDecode` décompressés, opérateurs texte lus |
| `.json` | deck exporté par l'app |

Les PDF scannés et les photos de tableau **ne sont pas lisibles ici** (il
faudrait la vision de Claude) : passe par la version desktop, qui les transcrit,
puis importe le deck.

## Ce que l'app fait

- Répétition espacée SM-2 identique à la version desktop (étapes 1 min / 10 min,
  quatre notes, délais affichés sur les boutons, carte ratée remise en fin de file)
- Flashcards (touche la carte pour révéler) et QCM auto-corrigés avec explication
- Examen blanc chronométré, une question par écran, correction récapitulative
  qui alimente le planning
- Missions du jour, série de jours, objectif quotidien
- Stats : activité sur 12 semaines, charge des 14 prochains jours, progression
  par matière
- Thème clair / sombre / automatique, export et effacement des données

## Développer

La source est **un seul fichier** : `app.body.html` (style + markup + script).
Après modification :

```bash
python3 revision/mobile/build.py       # régénère index.html et artifact.html
python3 revision/mobile/make_icons.py  # régénère les icônes (si le motif change)
```

- `index.html` — page complète installable (manifest, icônes, service worker)
- `artifact.html` — même app sans `<html>/<head>/<body>`, pour publication en artefact
- `sw.js` — met la coquille en cache ; bump `CACHE` à chaque changement visible

Ne modifie pas `index.html` ni `artifact.html` à la main : ils sont écrasés.
