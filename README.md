# 🎲 SpielBot

### Goal of Project

Those who know me know that I am a huge board game enthusiast. Now that I'm a few years into the hobby, one thing that always slows games things down is rules/edge-case disputes. Someone thinks they remember how something works, someone else disagrees, and suddenly half the table is passing a rulebook around trying to find the one paragraph that settles it. This was the core inspiration for me attempting to build SpielBot. I wanted something that could just answer in-game questions in plain English, quickly, and with appropriate references so that answers are reliable.

The idea is to combine RAG over official rulebooks and BoardGameGeek forum data with some vision-language model support, so you can also just show it a photo of your board and ask your question that way. Also, given my current coursework at school, I think it's a good excuse to learn more about RAG pipelines, multimodal models, and building something end-to-end that's pretty useful!

### What It Does 🗺️

- Answer rules questions in natural language
- Interpret photos of your current game state
- Ground answers in official rulebooks or community discussion
- Cite sources so you can verify conclusions (or win the argument)

---

## 📋 Roadmap -> To be updated

- [x] Project scoped and README drafted
- [ ] Repo structure and initial setup
- [ ] Data pipeline — PDF rulebook ingestion + BGG forum scraping
- [ ] RAG pipeline (chunking, embeddings, vector store)
- [ ] Core Q&A chain with citation retrieval
- [ ] VLM integration for game state image input
- [ ] Evaluation framework (rule accuracy, citation quality, visual comprehension)
- [ ] Frontend / user interface

## 📅 Progression

| Date | Details |
| ---- | ------- |
| 03/03/26 | Project started |