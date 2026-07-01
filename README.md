# 📊 Daily Stock Analysis

Analyse boursière automatique quotidienne, envoyée sous forme de brouillon Gmail.

## ⚙️ Fonctionnement

Ce projet ne contient plus de script à héberger. L'automatisation tourne via une
**Routine Claude Code** (claude.ai/code/routines) :

- **Trigger** : Scheduled, quotidien (jours de semaine, ~7h30)
- **Connecteur** : Gmail (création de brouillon, pas d'envoi automatique)
- **Prompt** : demande une analyse d'une action décotée, formatée en JSON puis en HTML,
  et crée un brouillon Gmail à destination de luc.renouvel@gmail.com

## 🔧 Pour ajuster

Modifie directement le prompt et le trigger dans la Routine sur claude.ai/code/routines
(heure d'exécution, format de l'email, critères de sélection de l'action, etc.).

## ⚠️ Avertissement

Informatif uniquement. Pas un conseil en investissement.
