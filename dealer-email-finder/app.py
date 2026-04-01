#!/usr/bin/env python3
"""FastAPI web application for the Dealer Email Finder."""
import asyncio
import json
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import config
import storage
from scraper_engine import engine
from utils import setup_logging

app = FastAPI(title="Dealer Email Finder", version="1.0.0")

# Ensure directories exist
os.makedirs('data/uploads', exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize DB on startup
@app.on_event("startup")
def startup():
    os.makedirs('data', exist_ok=True)
    storage.init_db()
    setup_logging(verbose=False)


# --- Models ---

class AddDealerRequest(BaseModel):
    company_name: str
    company_number: str = ""
    postcode: str = ""
    companies_house_url: str = ""
    registered_address: str = ""
    dealer_principal: str = ""


class StartRequest(BaseModel):
    batch_size: int = 100
    verify_mx: bool = False
    industry: str = ""
    company_numbers: Optional[List[str]] = None


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path("templates/index.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/upload")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        return {"error": "Please upload an Excel file (.xlsx)"}

    save_path = f"data/uploads/{file.filename}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    imported = storage.import_from_excel(save_path)
    stats = storage.get_progress_stats()
    return {"imported": imported, "filename": file.filename, "stats": stats}


@app.post("/api/add")
async def add_dealer(req: AddDealerRequest):
    cn = storage.insert_dealer(
        company_name=req.company_name,
        company_number=req.company_number or None,
        postcode=req.postcode,
        companies_house_url=req.companies_house_url,
        registered_address=req.registered_address,
    )
    stats = storage.get_progress_stats()
    return {"company_number": cn, "message": f"Added {req.company_name}", "stats": stats}


@app.post("/api/start")
async def start_scraping(req: StartRequest):
    if engine.running:
        return {"error": "Scraper is already running"}
    engine.start(
        batch_size=req.batch_size,
        verify_mx=req.verify_mx,
        industry=req.industry,
        company_numbers=req.company_numbers,
    )
    if req.company_numbers:
        return {"message": f"Started scraping {len(req.company_numbers)} selected companies"}
    industry_msg = f" (industry: {req.industry})" if req.industry else ""
    return {"message": f"Started scraping batch of {req.batch_size}{industry_msg}"}


@app.post("/api/stop")
async def stop_scraping():
    if not engine.running:
        return {"error": "Scraper is not running"}
    engine.stop()
    return {"message": "Stop requested"}


@app.get("/api/stats")
async def get_stats():
    stats = storage.get_progress_stats()
    stats['engine_status'] = engine.status
    stats['current_dealer'] = engine.current_dealer
    return stats


@app.get("/api/dealers")
async def get_dealers(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: str = Query("all"),
    search: str = Query(""),
):
    return storage.get_dealers_paginated(
        page=page, per_page=per_page,
        status_filter=status if status != "all" else None,
        search=search if search else None,
    )


@app.get("/api/dealers/all-numbers")
async def get_all_company_numbers(
    status: str = Query("all"),
    search: str = Query(""),
):
    """Get all company numbers matching current filters (for select-all across pages)."""
    numbers = storage.get_all_company_numbers(
        status_filter=status if status != "all" else None,
        search=search if search else None,
    )
    return {"company_numbers": numbers, "total": len(numbers)}


@app.delete("/api/dealers/{company_number}")
async def remove_dealer(company_number: str):
    storage.delete_dealer(company_number=company_number)
    return {"message": f"Deleted {company_number}"}


class ResetSelectedRequest(BaseModel):
    company_numbers: List[str]


@app.post("/api/reset")
async def reset_dealers():
    storage.reset_pending()
    stats = storage.get_progress_stats()
    return {"message": "Reset error/processing dealers to pending", "stats": stats}


@app.post("/api/reset-selected")
async def reset_selected(req: ResetSelectedRequest):
    """Reset specific dealers back to pending so they can be re-scraped."""
    if not req.company_numbers:
        return {"error": "No companies specified"}
    count = storage.reset_dealers_by_numbers(company_numbers=req.company_numbers)
    stats = storage.get_progress_stats()
    return {"message": f"Reset {count} dealers to pending", "count": count, "stats": stats}


@app.post("/api/clear")
async def clear_all():
    if engine.running:
        return {"error": "Cannot clear while scraper is running"}
    storage.clear_all()
    return {"message": "All dealers cleared"}


@app.get("/api/export")
async def export_excel():
    output = storage.export_to_excel()
    return FileResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="dealer_emails_export.xlsx",
    )


@app.get("/api/events")
async def sse_events():
    """Server-Sent Events endpoint for real-time updates."""
    q = engine.subscribe()

    async def event_generator():
        try:
            while True:
                try:
                    # Non-blocking check with small sleep
                    if not q.empty():
                        msg = q.get_nowait()
                        yield {"data": msg}
                    else:
                        await asyncio.sleep(0.3)
                except Exception:
                    break
        finally:
            engine.unsubscribe(q)

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn
    print(f"\n  Dealer Email Finder — http://localhost:{config.SERVER_PORT}\n")
    uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT, log_level="info")
