# 📚 Révisions — assistant d'étude local

> 📱 **Sur iPhone ?** Une version installable sur l'écran d'accueil, sans serveur,
> vit dans [`revision/mobile/`](mobile/README.md). Les deux versions échangent
> leurs cours par export/import JSON.

Application de révision inspirée d'Oria : tu déposes tes cours, Claude en tire des
**flashcards**, des **QCM**, une **fiche de révision** et une **mind map**, puis
l'app te fait réviser en **répétition espacée (SM-2)** avec missions quotidiennes,
examens blancs et statistiques.

Tout tourne en local : un serveur Python **sans aucune dépendance** (stdlib
uniquement) et un front vanilla. Tes cours ne quittent ta machine que pour les
appels à l'API Claude.

## 🚀 Démarrage

```bash
python3 revision/run.py --open        # http://127.0.0.1:8765
```

Pour activer l'IA (génération, transcription de PDF/photos, tuteur, correction) :

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 revision/run.py
```

Sans clé, l'app reste utilisable : import de texte, génération heuristique
hors-ligne (définitions repérées dans le cours), révision, examens, stats.

Options utiles :

| Commande | Effet |
| --- | --- |
| `--port 9000` | change le port |
| `--host 0.0.0.0` | accessible depuis ton téléphone sur le même Wi-Fi |
| `--open` | ouvre le navigateur automatiquement |
| `REVISION_DATA_DIR=/chemin` | déplace le stockage |
| `REVISION_VERBOSE=1` | logs HTTP |

## 📥 Formats acceptés

| Format | Traitement |
| --- | --- |
| `.txt` `.md` `.csv` `.html` | lecture directe |
| `.docx` `.pptx` `.odt` `.odp` | dézippage + extraction XML (stdlib) |
| `.pdf` | extraction du calque texte ; si le PDF est scanné, Claude le transcrit |
| `.png` `.jpg` `.webp` | transcription par Claude (photo de tableau, de manuel…) |
| copier-coller | bouton « Coller du texte » |

## 🧠 Comment ça révise

- **SM-2** avec étapes d'apprentissage (1 min, 10 min) puis intervalles croissants.
- 4 notes : `À revoir` / `Difficile` / `Correct` / `Facile` (raccourcis `1` à `4`,
  `Espace` pour révéler, `A`–`D` pour répondre à un QCM).
- Une carte notée « À revoir » repasse en fin de session.
- Les QCM sont auto-corrigés, les questions ouvertes d'examen sont notées par
  l'IA (note /100, verdict, points manquants) puis répercutées sur le planning.
- Le tableau de bord calcule l'objectif du jour, la série de jours consécutifs et
  des missions (file à vider, cours à générer, examen qui approche).

## 🗂️ Données

Tout est dans `revision/data/` (ignoré par git) :

- `store.json` — cours, cartes, historique de révisions, réglages
- `uploads/` — fichiers d'origine importés

Bouton **Exporter en JSON** dans Réglages pour une sauvegarde.

## 🧪 Tests

```bash
python3 -m unittest revision.tests.test_revision -v
```

19 tests : algorithme SM-2, extraction docx/pptx/pdf/images, cycle de vie des
cours et cartes, examen, parsing des réponses de l'IA.

## 🏗️ Architecture

```
revision/
├── run.py               # lanceur CLI
├── server/
│   ├── app.py           # routes HTTP + logique missions/stats
│   ├── ai.py            # API Claude (urllib) + génération hors-ligne
│   ├── extract.py       # extraction de texte multi-format
│   ├── srs.py           # répétition espacée SM-2
│   └── store.py         # persistance JSON atomique
├── web/                 # index.html + style.css + app.js (aucun build)
├── mobile/              # version installable sur téléphone, 100 % navigateur
└── tests/
```

La clé API est lue côté serveur uniquement : elle n'est jamais transmise au
navigateur. Le modèle est configurable dans Réglages (`claude-sonnet-5` par
défaut, `claude-opus-5` pour les cours difficiles, `claude-haiku-4.5` pour
l'économie).
