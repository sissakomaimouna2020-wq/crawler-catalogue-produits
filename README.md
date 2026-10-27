---
title: Mon Chatbot RAG
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# 🤖 Mini Chatbot RAG — Assistant IA Générative

Projet final réalisé dans le cadre du cours : Introduction aux IA Génératives.

## Fonctionnalités

- 💬 Chatbot RAG avec recherche TF-IDF
- 🧠 Génération de réponses avec FLAN-T5
- 🔍 Exploration du corpus
- 😊 Analyse de sentiment avec DistilBERT
- ✍️ Génération libre GPT-2
- ⚖️ Comparaison GPT-2 vs FLAN-T5
- ➕ Ajout de document à la volée
- 💾 Export de l'historique de conversation

## Technologies utilisées

- Python
- Gradio
- Hugging Face Transformers
- Scikit-learn / TF-IDF

## Déploiement

Application déployée sur Hugging Face Spaces.

## Structure

- `app.py` → interface Gradio
- `rag.py` → moteur RAG
- `corpus/` → base de connaissances (8 fichiers .txt)

## Auteurs

Projet M2 — IA Générative
