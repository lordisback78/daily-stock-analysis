# 📊 Daily Stock Analysis

Analyse boursière automatique quotidienne à 6h du matin.

## ⚙️ Setup complet

Tout est déjà configuré. Le workflow s'exécute automatiquement chaque jour à 6h.

## 🔧 Pour ajuster l'heure

Modifie le cron dans `.github/workflows/daily_stock_analysis.yml` ligne 6.
Exemples:
- `0 8 * * *` → 8h UTC
- `30 6 * * *` → 6h30 UTC

## 📝 Pour ajuster l'analyse

Modifie le `prompt` dans `daily_stock_analysis.py`.

## ⚠️ Avertissement

Informatif uniquement. Pas un conseil en investissement.

---

# ⌚ Garmin Data Sync

Récupère chaque matin (7h UTC) tes données Garmin Connect en lecture seule : entraînements, sommeil, HRV, fréquence cardiaque au repos, body battery, stress, training readiness. Les fichiers sont enregistrés dans `garmin_data/YYYY-MM-DD.json`.

## ⚙️ Setup

Ajoute deux secrets dans Settings → Secrets and variables → Actions :
- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

Le workflow `.github/workflows/garmin_sync.yml` s'occupe du reste.

## 🔧 Pour ajuster l'heure

Modifie le cron dans `.github/workflows/garmin_sync.yml` ligne 6.

---

# 📚 Révisions

Application de révision locale (façon Oria) : dépose tes cours (PDF, DOCX, PPTX,
photos, notes), Claude en tire flashcards, QCM, fiche de révision et mind map,
puis l'app te fait réviser en répétition espacée avec examens blancs et stats.

```bash
python3 revision/run.py --open
```

Détails, formats acceptés et options : [`revision/README.md`](revision/README.md).
