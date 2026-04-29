"""
JSEdge — FastAPI web application entry point.

Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000 in your browser.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="JSEdge",
    description="Long-term investment intelligence for the Jamaica Stock Exchange.",
    version="0.1.0",
)

# Tell FastAPI where the HTML templates live (app/templates/).
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """JSEdge landing page — defaults to the JSE tab."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request":     request,
            "active_tab":  "jse",
            "page_title":  "JSE — Stock Rankings",
        },
    )


@app.get("/news", response_class=HTMLResponse)
async def news(request: Request):
    """News tab — Phase 2 placeholder."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request":     request,
            "active_tab":  "news",
            "page_title":  "News — Coming in Phase 2",
        },
    )


@app.get("/trading", response_class=HTMLResponse)
async def trading(request: Request):
    """Trading tab — Phase 3 placeholder."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request":     request,
            "active_tab":  "trading",
            "page_title":  "Trading — Coming in Phase 3",
        },
    )


@app.get("/health")
async def health():
    """Health check endpoint — useful for deployment monitoring."""
    return {"status": "ok", "service": "jsedge", "version": "0.1.0"}