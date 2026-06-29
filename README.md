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
