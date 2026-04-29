# Next session

## Pick up here

1. **Step B (15 min):** Replace Trading tab placeholder in `app/templates/index.html` 
   with the richer roadmap card (4 feature cards). Code is in chat history.

2. **Step 3.3 — HTML Parser (60-90 min):** Parse `data/samples/main_2026-04-28.html` 
   to extract symbol, name, price, volume from the trade quotes table. 
   Use BeautifulSoup4. Test against saved sample, then run live.

3. **Step 3.4 — Save to database:** Insert parsed rows into `stocks` and 
   `prices_daily` tables.

## Current state

- 5 commits live. FastAPI server runs on `localhost:8000`. Database has 9 tables, 
  seeded settings. Scraper fetches HTML successfully. Sample HTML saved locally.
- Run `uvicorn app.main:app --reload` to start the server.
- Run `.\.venv\Scripts\Activate.ps1` if venv isn't active.