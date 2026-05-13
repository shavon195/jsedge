"""
JSEdge — FastAPI web application entry point.

Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000 in your browser.
"""

from pathlib import Path

from fastapi import FastAPI, Request, Form, Depends
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

# Make is_admin available globally to every template.
from app.auth import is_admin
from app.auth import require_admin
templates.env.globals["is_admin"] = is_admin

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
async def news(request: Request, flash: str = ""):
    """News tab — list scraped articles with their auto/manual tags."""
    from app.news.queries import list_recent_articles, list_all_stocks_for_dropdown

    articles    = list_recent_articles(limit=50)
    all_stocks  = list_all_stocks_for_dropdown()

    # Parse flash query param.
    flash_kind = None
    flash_msg  = None
    if flash.startswith("success_"):
        flash_kind = "success"
        flash_msg  = flash.replace("success_", "", 1)
    elif flash.startswith("error_"):
        flash_kind = "error"
        flash_msg  = flash.replace("error_", "", 1)

    return templates.TemplateResponse(
        "news.html",
        {
            "request":     request,
            "active_tab":  "news",
            "page_title":  "News",
            "articles":    articles,
            "all_stocks":  all_stocks,
            "flash_kind":  flash_kind,
            "flash_msg":   flash_msg,
        },
    )

@app.post("/news/tags/{link_id}/remove")
async def news_remove_tag(link_id: int,
                          _admin: bool = Depends(require_admin)):
    """Soft-delete a stock tag from a news article."""
    from app.news.queries import remove_tag
    from app.database import get_connection

    # Look up the article id for the redirect anchor BEFORE removing.
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT article_id FROM news_stock_links WHERE id = ?",
            (link_id,),
        ).fetchone()
    finally:
        conn.close()
    article_id = row["article_id"] if row else None

    ok = remove_tag(link_id)
    flash = "success_Tag+removed." if ok else "error_Tag+not+found+or+already+removed."
    anchor = f"#article-{article_id}" if article_id else ""
    return RedirectResponse(url=f"/news?flash={flash}{anchor}", status_code=303)

@app.post("/news/{article_id}/tags/add")
async def news_add_tag(article_id: int,
                       _admin: bool = Depends(require_admin),
                       stock_id: int = Form(...)):
    """Add a manual stock tag to a news article."""
    from app.news.queries import add_manual_tag
    new_id = add_manual_tag(article_id, stock_id)
    if new_id is None:
        flash = "error_That+tag+already+exists."
    else:
        flash = "success_Tag+added."
    return RedirectResponse(
        url=f"/news?flash={flash}#article-{article_id}",
        status_code=303,
    )

@app.post("/news/{article_id}/summarize")
async def news_summarize(article_id: int,
                         _admin: bool = Depends(require_admin)):
    """Generate an AI summary for the given article via Gemini."""
    from app.news.summarizer import summarize_article
    result = summarize_article(article_id)
    if result["ok"]:
        flash = "success_Summary+generated."
    else:
        # Keep the flash short but informative.
        err = (result["error"] or "Unknown error.")[:120]
        flash = "error_" + err.replace(" ", "+")
    return RedirectResponse(
        url=f"/news?flash={flash}#article-{article_id}",
        status_code=303,
    )

@app.post("/news/refresh")
async def news_refresh(_admin: bool = Depends(require_admin)):
    """Re-run the full news scrape pipeline (Gleaner + Observer)."""
    from app.news import scrape_gleaner_business, scrape_observer_business, save_articles_to_db

    try:
        gleaner_articles  = scrape_gleaner_business()
        observer_articles = scrape_observer_business()
        articles = gleaner_articles + observer_articles

        if not articles:
            flash = "error_No+articles+found+this+run."
        else:
            result = save_articles_to_db(articles)
            ins  = result["articles_inserted"]
            upd  = result["articles_updated"]
            auto = result["links_auto"]
            them = result["links_thematic"]
            flash = (
                f"success_Refreshed:+{ins}+new,+{upd}+updated."
                f"+Links:+{auto}+auto,+{them}+thematic."
            )
    except Exception as e:
        err = str(e)[:120].replace(" ", "+")
        flash = f"error_Scrape+failed:+{err}"

    return RedirectResponse(url=f"/news?flash={flash}", status_code=303)

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
# Admin auth
# ---------------------------------------------------------------------------
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_form(request: Request, next: str = "", error: str = ""):
    """Show the login form."""
    return templates.TemplateResponse(
        "admin_login.html",
        {
            "request":    request,
            "page_title": "Admin Login",
            "next":       next,
            "error":      error,
        },
    )


@app.post("/admin/login")
async def admin_login_submit(
    request: Request,
    password: str = Form(...),
    next: str    = Form(""),
):
    """Verify password; set session cookie on success."""
    from app.auth import login_user, SESSION_COOKIE, SESSION_MAX_AGE

    token = login_user(password)
    if token is None:
        # Bad password — re-render the form with an error.
        return templates.TemplateResponse(
            "admin_login.html",
            {
                "request":    request,
                "page_title": "Admin Login",
                "next":       next,
                "error":      "Incorrect password.",
            },
            status_code=401,
        )

    # Redirect to the `next` URL if it's a safe local path, otherwise home.
    target = next if next.startswith("/") else "/"
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie(
        key      = SESSION_COOKIE,
        value    = token,
        max_age  = SESSION_MAX_AGE,
        httponly = True,         # JS can't read the cookie (XSS protection)
        samesite = "lax",        # CSRF mitigation
        secure   = False,        # set True in production over HTTPS
    )
    return response


@app.post("/admin/logout")
async def admin_logout():
    """Clear the session cookie and redirect home."""
    from app.auth import SESSION_COOKIE

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=SESSION_COOKIE)
    return response

# ---------------------------------------------------------------------------
# Fundamentals data entry
# ---------------------------------------------------------------------------
@app.get("/fundamentals", response_class=HTMLResponse)
async def fundamentals_list(request: Request,
                            _admin: bool = Depends(require_admin)):
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
    _admin: bool = Depends(require_admin),
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
    _admin: bool = Depends(require_admin),
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
    _admin: bool = Depends(require_admin),
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
    _admin: bool = Depends(require_admin),
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
async def fundamental_delete(request: Request, fundamental_id: int,
                             _admin: bool = Depends(require_admin)):
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