"""Manus Ultra Hunter v3.5 + v4 — FastAPI Backend."""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.database import (
    init_db, seed_default_sources,
    get_all_settings, get_setting, set_setting,
    get_all_sources, get_source, upsert_source, delete_source,
    get_detections, get_detection_stats, get_unnotified_detections,
    reset_all_detections_and_snapshots,
)
from app.scheduler import scheduler
from app.notifier import send_test_notification, process_notification_queue
from app.source_registry import check_source
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application lifespan handler."""
    logger.info("Initializing Manus Ultra Hunter v3.5+v4...")
    await init_db()

    defaults = {
        "firecrawl_api_key_1": os.environ.get("FIRECRAWL_API_KEY_1", ""),
        "firecrawl_api_key_2": os.environ.get("FIRECRAWL_API_KEY_2", ""),
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "monitoring_enabled": "true",
    }
    for key, value in defaults.items():
        existing = await get_setting(key)
        if existing is None and value:
            await set_setting(key, value)

    await seed_default_sources()

    monitoring_enabled = await get_setting("monitoring_enabled")
    if monitoring_enabled == "true":
        await scheduler.start()
        logger.info("Monitoring scheduler auto-started")

    yield

    await scheduler.stop()
    logger.info("Manus Ultra Hunter shut down")


app = FastAPI(
    title="Manus Ultra Hunter v3.5+v4",
    description="360 AI Event Intelligence System",
    version="3.5.0",
    lifespan=lifespan
)

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


class SettingUpdate(BaseModel):
    key: str
    value: str


class SettingsBatchUpdate(BaseModel):
    settings: dict[str, str]


class SourceCreate(BaseModel):
    name: str
    url: str
    source_type: str = "webpage"
    check_interval_seconds: int = 60
    is_active: bool = True


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None
    check_interval_seconds: Optional[int] = None
    is_active: Optional[bool] = None


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/status")
async def get_status():
    stats = await get_detection_stats()
    sources = await get_all_sources()
    active_sources = [s for s in sources if s["is_active"]]
    error_sources = [s for s in sources if s["error_count"] > 0]
    return {
        "system": "Manus Ultra Hunter v3.5+v4",
        "status": "running" if scheduler.is_running else "stopped",
        "scheduler": scheduler.status,
        "sources": {
            "total": len(sources),
            "active": len(active_sources),
            "with_errors": len(error_sources),
        },
        "detections": stats,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/settings")
async def get_settings():
    settings = await get_all_settings()
    masked = {}
    sensitive_keys = ["firecrawl_api_key_1", "firecrawl_api_key_2",
                      "gemini_api_key", "telegram_bot_token"]
    for key, value in settings.items():
        if key in sensitive_keys and value:
            masked[key] = value[:8] + "..." + value[-4:] if len(value) > 12 else "****"
        else:
            masked[key] = value
    return {"settings": masked}


@app.get("/api/settings/raw")
async def get_settings_raw():
    settings = await get_all_settings()
    return {"settings": settings}


@app.put("/api/settings")
async def update_setting(data: SettingUpdate):
    await set_setting(data.key, data.value)
    logger.info(f"Setting updated: {data.key}")
    return {"status": "ok", "key": data.key}


@app.put("/api/settings/batch")
async def update_settings_batch(data: SettingsBatchUpdate):
    for key, value in data.settings.items():
        await set_setting(key, value)
    logger.info(f"Batch settings updated: {list(data.settings.keys())}")
    return {"status": "ok", "updated": list(data.settings.keys())}


@app.get("/api/sources")
async def list_sources(active_only: bool = False):
    sources = await get_all_sources(active_only=active_only)
    return {"sources": sources}


@app.get("/api/sources/{source_id}")
async def get_source_detail(source_id: int):
    source = await get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"source": source}


@app.post("/api/sources")
async def create_source(data: SourceCreate):
    source_id = await upsert_source(
        data.name, data.url, data.source_type,
        data.check_interval_seconds, data.is_active
    )
    return {"status": "ok", "source_id": source_id}


@app.put("/api/sources/{source_id}")
async def update_source(source_id: int, data: SourceUpdate):
    source = await get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    name = data.name or source["name"]
    url = data.url or source["url"]
    source_type = data.source_type or source["source_type"]
    interval = data.check_interval_seconds if data.check_interval_seconds is not None else source["check_interval_seconds"]
    active = data.is_active if data.is_active is not None else bool(source["is_active"])
    await upsert_source(name, url, source_type, interval, active)
    return {"status": "ok"}


@app.delete("/api/sources/{source_id}")
async def remove_source(source_id: int):
    source = await get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await delete_source(source_id)
    return {"status": "ok"}


@app.get("/api/detections")
async def list_detections(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    priority: Optional[str] = None,
    source_id: Optional[int] = None,
):
    detections = await get_detections(limit, offset, priority, source_id)
    return {"detections": detections, "count": len(detections)}


@app.get("/api/detections/stats")
async def detection_stats():
    stats = await get_detection_stats()
    return {"stats": stats}


@app.post("/api/scheduler/start")
async def start_scheduler():
    if scheduler.is_running:
        return {"status": "already_running"}
    await scheduler.start()
    await set_setting("monitoring_enabled", "true")
    return {"status": "started"}


@app.post("/api/scheduler/stop")
async def stop_scheduler():
    if not scheduler.is_running:
        return {"status": "already_stopped"}
    await scheduler.stop()
    await set_setting("monitoring_enabled", "false")
    return {"status": "stopped"}


@app.get("/api/scheduler/status")
async def scheduler_status():
    return scheduler.status


@app.post("/api/actions/check/{source_id}")
async def trigger_source_check(source_id: int):
    source = await get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    result = await scheduler.trigger_check(source_id)
    return {"result": result}


@app.post("/api/actions/check-all")
async def trigger_check_all():
    results = await scheduler.trigger_check_all()
    return {"results": results}


@app.post("/api/actions/send-notifications")
async def trigger_notifications():
    count = await process_notification_queue()
    return {"notifications_sent": count}


@app.post("/api/actions/test-telegram")
async def test_telegram():
    success = await send_test_notification()
    if success:
        return {"status": "ok", "message": "Test notification sent"}
    raise HTTPException(status_code=500, detail="Failed to send test notification")


@app.post("/api/actions/reset")
async def reset_system():
    """Clear all old detections and snapshots to start fresh."""
    await reset_all_detections_and_snapshots()
    logger.info("System reset: all detections and snapshots cleared")
    return {"status": "ok", "message": "All detections and snapshots cleared. Next scan will establish fresh baseline."}


@app.get("/api/dashboard")
async def dashboard():
    stats = await get_detection_stats()
    sources = await get_all_sources()
    recent = await get_detections(limit=10)
    unnotified = await get_unnotified_detections()
    active_sources = [s for s in sources if s["is_active"]]
    error_sources = [s for s in sources if s["error_count"] > 0]
    return {
        "system": {
            "name": "Manus Ultra Hunter v3.5+v4",
            "version": "3.5.0",
            "status": "running" if scheduler.is_running else "stopped",
        },
        "stats": stats,
        "sources": {
            "total": len(sources),
            "active": len(active_sources),
            "with_errors": len(error_sources),
            "list": sources
        },
        "recent_detections": recent,
        "pending_notifications": len(unnotified),
        "scheduler": scheduler.status,
        "timestamp": datetime.utcnow().isoformat()
    }
