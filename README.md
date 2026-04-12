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
- [x] Processing script for rulebook data; section-based chunking?
- [x] Chunking script (preparation and execution)
- [x] Chunk embedding with ChromaDB vector store
- [x] Implement dense and sparse retrievers (BM25)
- [x] RAG orchestrator script (Use CMU LiteLLM instance)
- [ ] Image and text encoder (might use Gemma)
- [ ] VLM inference pipeline (access LlaVa or more SOTA/free VLM through Groq)
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
| 04/05/26| Implemented chunking script for rulebook outputs and cleaned up data file structure. I might need to revise the chunking strategies to make sure only useful information is being kept to support retriever quality |
| 04/06/26| Manually re-format PDF extractions of rulebooks (and get rid of 2 ROOT rulebooks) to ensure better chunk quality. Multi-column structures are difficult for `PDFPlumber` and I need to move faster for the sake of time. Also implemented the embedding script to embed chunks and store them into a ChromaDB instance |
| 04/07/26 | Refined chunking strategy to retain semantic sense through a given ruleset. Implemented dense (ChromaDB) and sparse (BM25) retrievers for the hybrid retrieval approach. |
| 04/08/26 | Retriever is functional, but only retrieving rule-excerpts; made edits to force both rule and forum chunks to be retrieved so answers reflect ground truth _and_ community sentiment |
| 04/09/26 | Updated ROOT rulebook with Homeland Expansion Law as well as custom curated card dataset with information on every card across the 3 decks available. |
| 04/11/26 | Implemented generator component and stitched system together with `orchestrator.py` to support a CLI-based V1 implementation of SpielBot! |

## Future Considerations
 - **Extraction Generalizability** - Make extraction pipeline work over majority of rulebook formats with minimal game-specific revisions
 - **Better quality PDF extraction** - PDF Plumber struggles with multi-column data (a common rulebook format) and for testing purposes it is easier to just manually review and edit each rulebook. I'll need to look into other OCR libraries when I have time (PyPDF, Pytesseract, etc.)
- **Expanding on the evaluation dataset** - I think there is some real potential to make the evaluation dataset some kind of gold standard evaluation set for many more games to test LLM capabilities on rule following, synthesis, and reasoning!


### References

- [PDF Plumber](https://github.com/jsvine/pdfplumber)
- [BGG API Repo](https://github.com/tnaskali/bgg-api)
- [Using the BGG XML API](https://boardgamegeek.com/wiki/page/BGG_XML_API#)
- [ChromaDB](https://docs.trychroma.com/docs/overview/introduction)