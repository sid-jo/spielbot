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

## 📋 Roadmap

- [x] Repo structure and initial setup
- [x] Text Q&A evaluation dataset curated
- [x] Image-text dataset curated
- [x] Baseline outputs collected across ChatGPT, Claude, Gemini, and DeepSeek
- [x] Data pipeline — PDF rulebook ingestion + BGG forum scraping
- [x] Processing script for BGG data to prep for question-based embedding
- [ ] Processing script for rulebook data; section-based chunking?
- [ ] Chunking script (preparation and execution)
- [ ] Chunk embedding with vector store for dense and sparse retrievers
- [ ] RAG orchestrator script (Use Groq `Llama-32B-Instruct` or CMU LiteLLM instance)
- [ ] Image and text encoder (might use CLIP)
- [ ] VLM inference pipeline (access LlaVa or more SOTA VLM through Groq)
- [ ] Evaluation framework (rule accuracy, citation quality, visual comprehension, etc.)
- [ ] Implement UI mockup + game selection menu



## 📅 Progression

| Date | Details |
| ---- | ------- |
| 03/03/26 | Project started |
| 03/16/26 | Identified `PDFPlumber` and made initial rule extraction pipeline |
| 03/23/26 | Enhanced the rulebook extraction pipeline to work on multi-column pages, still working out tabular data |
| 03/24/26 | Requested BGG API key (would take about a week). Working on alternate webscraping component (`scrape_bgg_temp.py`) that uses geekdo API | 
| 03/25/26 | Got access to the BGG API and made the API key! Incorporated API calls to gather data and kept webscraping script as fallback| 
| 03/31/26 | Finalized BGG forum extraction script + processing script to prepare for chunking |
### References

- [PDF Plumber](https://github.com/jsvine/pdfplumber)
- [BGG API Repo](https://github.com/tnaskali/bgg-api)
- [Using the BGG XML API](https://boardgamegeek.com/wiki/page/BGG_XML_API#)