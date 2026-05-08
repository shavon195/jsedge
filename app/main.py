"""
JSEdge — FastAPI web application entry point.

Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000 in your browser.
"""

from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
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
async def home(request: Request, horizon: str = ""):
    """JSEdge landing page — JSE tab with horizon-aware rankings."""
    from app.ranking import get_latest_rankings, HORIZON_WEIGHTS, DEFAULT_HORIZON

    # Validate horizon param: must be one of the known horizons.
    # Empty/invalid -> use the default (10_years).
    if horizon not in HORIZON_WEIGHTS:
        horizon = DEFAULT_HORIZON

    rankings = get_latest_rankings(limit=25, horizon=horizon)

    return templates.TemplateResponse(
        "index.html",
        {
            "request":         request,
            "active_tab":      "jse",
            "page_title":      "JSE — Stock Rankings",
            "rankings":        rankings,
            "horizon":         horizon,
            "horizons_avail":  list(HORIZON_WEIGHTS.keys()),
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
async def fundamentals_for_stock(
    request: Request,
    stock_id: int,
    flash: str = "",
):
    """Show one stock's fundamentals + form to add a new period."""
    from app.fundamentals import get_stock_with_fundamentals, get_prev_next_stocks
    data = get_stock_with_fundamentals(stock_id)
    nav = get_prev_next_stocks(stock_id)

    if data is None:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "page_title": "Stock not found"},
            status_code=404,
        )

    # Parse the flash query param into something the template can use.
    flash_kind   = None    # 'success' or 'error'
    flash_msg    = None
    if flash.startswith("saved_"):
        flash_kind = "success"
        action     = flash.replace("saved_", "")
        flash_msg  = f"Period {action} successfully."
    elif flash.startswith("error_"):
        flash_kind = "error"
        flash_msg  = flash.replace("error_", "", 1)

    return templates.TemplateResponse(
        "fundamentals_stock.html",
        {
            "request":      request,
            "page_title":   f"{data['stock']['symbol']} — Fundamentals",
            "stock":        data["stock"],
            "fundamentals": data["fundamentals"],
            "nav":          nav,
            "flash_kind":   flash_kind,
            "flash_msg":    flash_msg,
        },
    )

@app.post("/fundamentals/stock/{stock_id}/save")
async def save_fundamental_period(
    request: Request,
    stock_id: int,
    action: str = Form("save"),
    period_end_date: str = Form(...),
    period_type:     str = Form(...),
    eps:                 str = Form(""),
    pe_ratio:            str = Form(""),
    pb_ratio:            str = Form(""),
    dividend_yield:      str = Form(""),
    total_debt:          str = Form(""),
    total_equity:        str = Form(""),
    total_assets:        str = Form(""),
    net_income:          str = Form(""),
    operating_income:    str = Form(""),
    operating_cash_flow: str = Form(""),
    free_cash_flow:      str = Form(""),
    revenue:             str = Form(""),
    shares_outstanding:  str = Form(""),
    notes:               str = Form(""),
):
    """Save (insert or update) one fundamentals period for a stock."""
    from app.fundamentals import save_fundamental

    form_data = {
        "period_end_date":     period_end_date,
        "period_type":         period_type,
        "eps":                 eps,
        "pe_ratio":            pe_ratio,
        "pb_ratio":            pb_ratio,
        "dividend_yield":      dividend_yield,
        "total_debt":          total_debt,
        "total_equity":        total_equity,
        "total_assets":        total_assets,
        "net_income":          net_income,
        "operating_income":    operating_income,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow":      free_cash_flow,
        "revenue":             revenue,
        "shares_outstanding":  shares_outstanding,
        "notes":               notes,
    }

    result = save_fundamental(stock_id, form_data)

    # Build a query string with the result so the GET page can show a flash banner.
    if result["success"]:
        flash_msg = f"saved_{result['action']}"  # 'saved_inserted' or 'saved_updated'
    else:
        # Join errors into a single short string for the URL.
        flash_msg = "error_" + " | ".join(result["errors"])

    # Redirect back to the stock's fundamentals page (PRG pattern).
    # If the user clicked "Save and Add Another", append #add-period so
    # the browser auto-scrolls to the form.
    redirect_url = f"/fundamentals/stock/{stock_id}?flash={flash_msg}"
    if action == "save_and_add" and result["success"]:
        redirect_url += "#add-period"

    return RedirectResponse(
        url=redirect_url,
        status_code=303,  # 303 = redirect a POST to a GET
    )

@app.get("/fundamentals/period/{fundamental_id}", response_class=HTMLResponse)
async def fundamental_view(
    request: Request,
    fundamental_id: int,
    flash: str = "",
):
    """View one fundamentals row (read-only) with edit form."""
    from app.fundamentals import get_fundamental_by_id
    f = get_fundamental_by_id(fundamental_id)

    if f is None:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "page_title": "Period not found"},
            status_code=404,
        )

    # Parse flash query param.
    flash_kind = None
    flash_msg  = None
    if flash.startswith("saved_"):
        flash_kind = "success"
        action     = flash.replace("saved_", "")
        flash_msg  = f"Period {action} successfully."
    elif flash.startswith("error_"):
        flash_kind = "error"
        flash_msg  = flash.replace("error_", "", 1)

    return templates.TemplateResponse(
        "fundamental_view.html",
        {
            "request":    request,
            "page_title": f"{f['symbol']} — {f['period_end_date']}",
            "f":          f,
            "flash_kind": flash_kind,
            "flash_msg":  flash_msg,
        },
    )


@app.post("/fundamentals/period/{fundamental_id}/update")
async def fundamental_update(
    request: Request,
    fundamental_id: int,
    period_end_date: str = Form(...),
    period_type:     str = Form(...),
    eps:                 str = Form(""),
    pe_ratio:            str = Form(""),
    pb_ratio:            str = Form(""),
    dividend_yield:      str = Form(""),
    total_debt:          str = Form(""),
    total_equity:        str = Form(""),
    total_assets:        str = Form(""),
    net_income:          str = Form(""),
    operating_income:    str = Form(""),
    operating_cash_flow: str = Form(""),
    free_cash_flow:      str = Form(""),
    revenue:             str = Form(""),
    shares_outstanding:  str = Form(""),
    notes:               str = Form(""),
):
    """Update an existing fundamentals row."""
    from app.fundamentals import save_fundamental, get_fundamental_by_id

    existing = get_fundamental_by_id(fundamental_id)
    if existing is None:
        return RedirectResponse(url="/fundamentals", status_code=303)

    form_data = {
        "period_end_date":     period_end_date,
        "period_type":         period_type,
        "eps":                 eps,
        "pe_ratio":            pe_ratio,
        "pb_ratio":            pb_ratio,
        "dividend_yield":      dividend_yield,
        "total_debt":          total_debt,
        "total_equity":        total_equity,
        "total_assets":        total_assets,
        "net_income":          net_income,
        "operating_income":    operating_income,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow":      free_cash_flow,
        "revenue":             revenue,
        "shares_outstanding":  shares_outstanding,
        "notes":               notes,
    }
    result = save_fundamental(existing["stock_id"], form_data)

    if result["success"]:
        flash_msg = "saved_updated"
    else:
        flash_msg = "error_" + " | ".join(result["errors"])

    return RedirectResponse(
        url=f"/fundamentals/period/{fundamental_id}?flash={flash_msg}",
        status_code=303,
    )


@app.post("/fundamentals/period/{fundamental_id}/delete")
async def fundamental_delete(request: Request, fundamental_id: int):
    """Delete a fundamentals row, then redirect back to the stock page."""
    from app.fundamentals import get_fundamental_by_id, delete_fundamental

    existing = get_fundamental_by_id(fundamental_id)
    if existing is None:
        return RedirectResponse(url="/fundamentals", status_code=303)

    stock_id = existing["stock_id"]
    delete_fundamental(fundamental_id)

    return RedirectResponse(
        url=f"/fundamentals/stock/{stock_id}?flash=saved_deleted",
        status_code=303,
    )