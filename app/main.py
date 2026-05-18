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
async def home(request: Request, horizon: str = "", flash: str = ""):
    """JSEdge landing page — JSE tab with horizon-aware rankings."""
    from app.ranking import get_latest_rankings, HORIZON_WEIGHTS, DEFAULT_HORIZON
    from app.watchlist import get_watched_symbols
    # Validate horizon param: must be one of the known horizons.
    # Empty/invalid -> use the default (10_years).
    if horizon not in HORIZON_WEIGHTS:
        horizon = DEFAULT_HORIZON

    rankings = get_latest_rankings(limit=25, horizon=horizon)
    watched  = get_watched_symbols()  # set of symbols already on watchlist
    # Parse flash query param (used after "Add to watchlist" actions).
    flash_kind = None
    flash_msg  = None
    if flash.startswith("success_"):
        flash_kind = "success"
        flash_msg  = flash.replace("success_", "", 1)
    elif flash.startswith("error_"):
        flash_kind = "error"
        flash_msg  = flash.replace("error_", "", 1)

    return templates.TemplateResponse(
        "index.html",
        {
            "request":         request,
            "active_tab":      "jse",
            "page_title":      "JSE — Stock Rankings",
            "rankings":        rankings,
            "horizon":         horizon,
            "horizons_avail":  list(HORIZON_WEIGHTS.keys()),
            "watched":         watched,
            "flash_kind":      flash_kind,
            "flash_msg":       flash_msg,
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
# Watchlist (admin-only)
# ---------------------------------------------------------------------------
@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist_view(request: Request,
                         state: str = "active",
                         flash: str = "",
                         _admin: bool = Depends(require_admin)):
    """Show the watchlist."""
    from app.watchlist import list_watchlist, watchlist_counts, get_price_context

    # Validate state param.
    if state not in ("active", "inactive", "hit", "all"):
        state = "active"

    # 'hit' is a derived state — show actives, filtered to hit targets.
    if state == "hit":
        all_active = list_watchlist(state="active")
        rows = [w for w in all_active if w["gap_state"] == "hit"]
    else:
        rows = list_watchlist(state=state)

    # Enrich each row with price context for the expand panel.
    for w in rows:
        w["context"] = get_price_context(w["stock_id"])

    counts = watchlist_counts()

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
        "watchlist.html",
        {
            "request":     request,
            "active_tab":  "watchlist",
            "page_title":  "Watchlist",
            "rows":        rows,
            "counts":      counts,
            "state":       state,
            "flash_kind":  flash_kind,
            "flash_msg":   flash_msg,
        },
    )


@app.post("/watchlist/add")
async def watchlist_add(symbol: str = Form(...),
                        _admin: bool = Depends(require_admin)):
    """Add a stock to the watchlist (called from the JSE rankings page)."""
    from app.watchlist import add_to_watchlist_by_symbol

    new_id = add_to_watchlist_by_symbol(symbol)
    if new_id is None:
        # Could be "unknown symbol" or "already watched"; treat both as
        # a soft error since the user-facing outcome is the same.
        flash = f"error_Could+not+add+{symbol}+(already+watched+or+unknown)."
    else:
        flash = f"success_Added+{symbol}+to+watchlist."
    return RedirectResponse(url=f"/?flash={flash}", status_code=303)

@app.post("/watchlist/{watchlist_id}/update")
async def watchlist_update(watchlist_id: int,
                           _admin: bool = Depends(require_admin),
                           limit_price: str = Form(""),
                           notes: str = Form(""),
                           is_active: str = Form("")):
    """Update a watchlist row (target price / notes / pause)."""
    from app.watchlist import update_watchlist

    kwargs = {}
    if limit_price.strip():
        try:
            kwargs["limit_price"] = float(limit_price)
        except ValueError:
            return RedirectResponse(
                url="/watchlist?flash=error_Invalid+price.",
                status_code=303,
            )
    if notes:
        kwargs["notes"] = notes
    if is_active in ("0", "1"):
        kwargs["is_active"] = (is_active == "1")

    update_watchlist(watchlist_id, **kwargs)
    return RedirectResponse(
        url="/watchlist?flash=success_Updated.",
        status_code=303,
    )


@app.post("/watchlist/{watchlist_id}/remove")
async def watchlist_remove(watchlist_id: int,
                           _admin: bool = Depends(require_admin)):
    """Delete a watchlist row."""
    from app.watchlist import remove_from_watchlist

    ok = remove_from_watchlist(watchlist_id)
    flash = "success_Removed." if ok else "error_Not+found."
    return RedirectResponse(url=f"/watchlist?flash={flash}", status_code=303)

# ---------------------------------------------------------------------------
# Alert history (admin-only)
# ---------------------------------------------------------------------------
@app.get("/alerts", response_class=HTMLResponse)
async def alerts_view(request: Request,
                      filter: str = "all",
                      _admin: bool = Depends(require_admin)):
    """Show alert history (newest first)."""
    from app.alerts.dispatcher import list_alerts, alert_counts

    if filter not in ("all", "target_hit", "keep_alive", "failed"):
        filter = "all"

    rows   = list_alerts(filter_type=filter, limit=200)
    counts = alert_counts()

    return templates.TemplateResponse(
        "alerts.html",
        {
            "request":     request,
            "active_tab":  "alerts",
            "page_title":  "Alerts — History",
            "rows":        rows,
            "counts":      counts,
            "filter":      filter,
        },
    )

# ---------------------------------------------------------------------------
# Settings (admin-only)
# ---------------------------------------------------------------------------
@app.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request,
                        flash: str = "",
                        edit: str = "",
                        _admin: bool = Depends(require_admin)):
    """Show the settings page with all credentials + test buttons."""
    from app.settings import list_settings

    settings = list_settings()

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
        "settings.html",
        {
            "request":     request,
            "active_tab":  "settings",
            "page_title":  "Settings",
            "settings":    settings,
            "edit_key":    edit,
            "flash_kind":  flash_kind,
            "flash_msg":   flash_msg,
        },
    )


@app.post("/settings/save")
async def settings_save(key: str = Form(...),
                        value: str = Form(""),
                        _admin: bool = Depends(require_admin)):
    """Save (upsert) one setting value."""
    from app.settings import save_setting, EDITABLE_KEYS

    # Whitelist check — only allow saving keys we expose on the UI.
    valid_keys = {k for k, _, _ in EDITABLE_KEYS}
    if key not in valid_keys:
        return RedirectResponse(
            url=f"/settings?flash=error_Unknown+setting+{key}.",
            status_code=303,
        )

    save_setting(key, value.strip())
    return RedirectResponse(
        url=f"/settings?flash=success_Saved+{key}.",
        status_code=303,
    )


@app.post("/settings/test-email")
async def settings_test_email(_admin: bool = Depends(require_admin)):
    """Send a test email to confirm the channel works."""
    from app.alerts.email import send_test_email

    result = send_test_email()
    if result["ok"]:
        flash = f"success_Test+email+sent+(id+{result.get('id', 'unknown')[:8]}).+Check+your+inbox."
    else:
        err = (result.get("error") or "Unknown")[:100].replace(" ", "+")
        flash = f"error_Email+failed:+{err}"
    return RedirectResponse(url=f"/settings?flash={flash}", status_code=303)


@app.post("/settings/test-whatsapp")
async def settings_test_whatsapp(_admin: bool = Depends(require_admin)):
    """Send a test WhatsApp to confirm the channel works."""
    from app.alerts.whatsapp import send_test_whatsapp

    result = send_test_whatsapp()
    if result["ok"]:
        flash = f"success_Test+WhatsApp+sent+(sid+{result.get('sid', 'unknown')[:8]}).+Check+your+phone."
    else:
        err = (result.get("error") or "Unknown")[:100].replace(" ", "+")
        flash = f"error_WhatsApp+failed:+{err}"
    return RedirectResponse(url=f"/settings?flash={flash}", status_code=303)

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
    dividend_per_share:  str = Form(""),
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
        "dividend_per_share":  dividend_per_share,
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
    from app.database import get_connection

    f = get_fundamental_by_id(fundamental_id)

    if f is None:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "page_title": "Period not found"},
            status_code=404,
        )

    # Fetch the latest close price for live ratio computation.
    # Ratios are computed here (not stored) so they always reflect today's
    # price, not whatever the price was when fundamentals were entered.
    conn = get_connection()
    try:
        price_row = conn.execute(
            """
            SELECT close_price, date
            FROM prices_daily
            WHERE stock_id = ?
            ORDER BY date DESC LIMIT 1
            """,
            (f["stock_id"],),
        ).fetchone()
    finally:
        conn.close()

    latest_price = price_row["close_price"] if price_row else None
    latest_price_date = price_row["date"] if price_row else None

    # Compute the three derived ratios. Any missing input -> None.
    # Note: we explicitly check `is not None` (not truthiness) because a
    # legitimately-zero value (e.g. company paid no dividend this year) is
    # a real signal, not missing data. Without this, 0 would display as —.
    pe_ratio = None
    pb_ratio = None
    dividend_yield = None

    if latest_price and latest_price > 0:
        if f.get("eps") is not None and f["eps"] != 0:
            pe_ratio = latest_price / f["eps"]

        if (f.get("total_equity") is not None and f["total_equity"] > 0
                and f.get("shares_outstanding") is not None
                and f["shares_outstanding"] > 0):
            book_value_per_share = f["total_equity"] / f["shares_outstanding"]
            if book_value_per_share > 0:
                pb_ratio = latest_price / book_value_per_share

        if f.get("dividend_per_share") is not None:
            dividend_yield = (f["dividend_per_share"] / latest_price) * 100
    derived = {
        "latest_price":      latest_price,
        "latest_price_date": latest_price_date,
        "pe_ratio":          pe_ratio,
        "pb_ratio":          pb_ratio,
        "dividend_yield":    dividend_yield,
    }

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
            "derived":    derived,
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
    dividend_per_share:  str = Form(""),
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
        "dividend_per_share":  dividend_per_share,
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