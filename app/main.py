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
    """JSEdge landing page — defaults to the JSE tab with latest rankings."""
    from app.ranking import get_latest_rankings
    rankings = get_latest_rankings(limit=25)

    return templates.TemplateResponse(
        "index.html",
        {
            "request":     request,
            "active_tab":  "jse",
            "page_title":  "JSE — Stock Rankings",
            "rankings":    rankings,
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


# ---------------------------------------------------------------------------
# Fundamentals data entry
# ---------------------------------------------------------------------------
@app.get("/fundamentals", response_class=HTMLResponse)
async def fundamentals_list(request: Request):
    """Show all stocks + how many fundamental rows each has."""
    from app.fundamentals import list_stocks_with_status
    stocks = list_stocks_with_status()

    return templates.TemplateResponse(
        "fundamentals_list.html",
        {
            "request":    request,
            "page_title": "Fundamentals — Data Entry",
            "stocks":     stocks,
        },
    )

@app.get("/fundamentals/stock/{stock_id}", response_class=HTMLResponse)
async def fundamentals_for_stock(request: Request, stock_id: int):
    """Show one stock's fundamentals + form to add a new period."""
    from app.fundamentals import get_stock_with_fundamentals
    data = get_stock_with_fundamentals(stock_id)

    if data is None:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "page_title": "Stock not found"},
            status_code=404,
        )

    return templates.TemplateResponse(
        "fundamentals_stock.html",
        {
            "request":      request,
            "page_title":   f"{data['stock']['symbol']} — Fundamentals",
            "stock":        data["stock"],
            "fundamentals": data["fundamentals"],
        },
    )