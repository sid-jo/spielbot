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

## Quick Start (For running locally)

SpielBot’s main UI is the **React app** in [`frontend/`](frontend/) talking to a **FastAPI** server ([`api/main.py`](api/main.py)). Run **two processes**: the API first, then the frontend.

### Prerequisites

- **Python 3.10+** ([`conda`](https://docs.conda.io/) virtual environment recommended)
- **Node.js 18+** and **npm**
- **LiteLLM** (or another OpenAI-compatible gateway): base URL and API key. Put them in `.env` as below.
- The repo includes [`data/`](data/) (chunks and indexes). The first API startup may take a minute while embedding models load.

### 1. Configure environment

From the **repository root**, create `.env` from the example.

Edit `.env` and set at least:

- `LITELLM_BASE_URL` — your gateway URL (no trailing slash)
- `LITELLM_API_KEY` — your key  
- `SPIELBOT_REASON_MODEL` and `SPIELBOT_GEN_MODEL` if you differ from the examples

For the frontend, same idea: copy `frontend/.env.example` to `frontend/.env` (e.g. `Copy-Item frontend\.env.example frontend\.env` in PowerShell).

Keep `VITE_API_BASE_URL=/api` for local development. Vite proxies `/api` to the FastAPI process (see [`frontend/vite.config.ts`](frontend/vite.config.ts)), so the browser does not hit CORS issues. If you change `frontend/.env`, restart `npm run dev`.

### 2. Install Python dependencies and start the API

In the repo root (Within the `conda` venv):

```bash
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Leave this terminal open. Wait until the server is ready (first load can be slow while indexes and models initialize).

### 3. Install frontend dependencies and start Vite

In a **second** terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually **http://localhost:5173**) and you'll see SpielBot!

---

## 📋 Roadmap

- [x] Repo structure and initial setup
- [x] Text Q&A evaluation dataset curated
- [x] Baseline outputs collected across ChatGPT, Claude, Gemini, and DeepSeek
- [x] Data pipeline — PDF rulebook ingestion + BGG forum scraping
- [x] Processing script for BGG data to prep for question-based embedding
- [x] Processing script for rulebook data; section-based chunking?
- [x] Chunking script (preparation and execution)
- [x] Chunk embedding with ChromaDB vector store
- [x] Implement dense and sparse retrievers (BM25)
- [x] RAG orchestrator script (Use CMU LiteLLM instance)
- [x] Image-text dataset curated
- [x] VLM inference pipeline (to be done via Gemini)
- [x] Evaluation framework (rule accuracy, citation quality, visual comprehension, etc.)
- [x] Implement UI mockup + game selection menu
- [x] Iterate over UI to make it decent (explore Lovable)


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
| 04/12/26 | Created custom evaluation dataset! |
| 04/13/26 | Finished bullk of evaluation pipeline aside from the reporting scripts. Got initial results for each of the experiment modes and Spielbot is sadly not doing better than GPT with the PDF attachment, but is comparable with other methods. |
| 04/14/26 | Curated binary question-image dataset for VLM capability testing. Will be implementing VLM via Gemma tomorrow. Planning to evaluate on existing board game rule assistants as an additional baseline. |
| 04/16/26 | Incorporated vision component and revamped original retrieval to run multi-query retrieval to improve relevant chunk capture. Final results on evaluation data have been generated. |
| 04/18/26 | First draft of UI implemented in `streamlit` and it needs a TON of improvement in terms of response latency and general cleanliness of the site |
| 04/19/26 | Revamped front-end with Lovable and integrated into the backend. Used React + FastAPI for implementation. Spielbot-V1 is complete! |



## Future Considerations
 - **Extraction Generalizability** - Make extraction pipeline work over majority of rulebook formats with minimal game-specific revisions
 - **Better quality PDF extraction** - PDF Plumber struggles with multi-column data (a common rulebook format) and for testing purposes it is easier to just manually review and edit each rulebook. I'll need to look into other OCR libraries when I have time (PyPDF, Pytesseract, etc.)
- **Expanding on the evaluation dataset** - I think there is some real potential to make the evaluation dataset some kind of gold standard evaluation set for many more games to test LLM capabilities on rule following, synthesis, and reasoning!
- **Look into richer/better retrieval** - It might be worth it to explore more clever retrieval systems that are specialized on baord game rule data. While I don't think I will be able to rival the PDF extraction and retrieval capabilities of SOTA chatbots, I would like to come as close to them as possible with a fraction of the cost and much higher utility. The value prop for Spielbot could still stand in the lack of PDF upload by the user, board state image understanding, and cheaper/faster retrieval than SOTA chatbots.
- **Scenario-based Evalation** - Right now, have curated questions to fall into two categories: comprehension and reasoning. Comprehension questions are ideally questions that can be answered with a lookup to a single chunk and reasoning questions require synthesizing across chunks to create responses. I would like to explore scenario questions that lay out a sequence of events in a game and ask if a subsequent set of actions is possible. This could test the model's ability to follow the action trajectory, map it to relevant rule interactions, and validate the sequence of actions being proposed by the user.
- **Smarter chunking** - As of now, I am chunking rulebooks based on the section-by-section outline in which they are typically presented. No chunks overlap with one another and the system seems to be running into a sort of "needle in a haystack" problem where longer sections (chunks) with one crucial component to answer a question _don't_ get retrieved. And even if they are on occasion, there is too much noise within the chunk for the generator to pull out relevant details when crafting answers. So it might be worthwhile to explore a more granular chunking method that separates concepts within chunks a beyond the provided sectioning inherently in rulebooks.


### References

- [PDF Plumber](https://github.com/jsvine/pdfplumber)
- [BGG API Repo](https://github.com/tnaskali/bgg-api)
- [Using the BGG XML API](https://boardgamegeek.com/wiki/page/BGG_XML_API#)
- [ChromaDB](https://docs.trychroma.com/docs/overview/introduction)