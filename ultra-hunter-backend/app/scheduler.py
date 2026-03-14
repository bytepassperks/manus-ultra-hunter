"""Async scheduler engine for periodic source monitoring."""
import asyncio
from datetime import datetime
from typing import Optional

from app.database import get_all_sources, get_setting
from app.source_registry import check_source, _auto_register_discovered_sources
from app.notifier import process_notification_queue
from app.firecrawl_client import probe_live_event_urls
from app.utils.logger import logger


class MonitorScheduler:
    """Manages periodic monitoring of all sources."""

    def __init__(self):
        self._tasks: dict[int, asyncio.Task] = {}
        self._notification_task: Optional[asyncio.Task] = None
        self._running = False
        self._check_count = 0
        self._last_check_results: dict[int, dict] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> dict:
        active_tasks = sum(1 for t in self._tasks.values() if not t.done())
        return {
            "running": self._running,
            "active_source_tasks": active_tasks,
            "total_checks": self._check_count,
            "last_results": self._last_check_results
        }

    async def start(self):
        """Start the monitoring scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        logger.info("Starting monitoring scheduler...")

        # Start notification processor
        self._notification_task = asyncio.create_task(
            self._notification_loop(),
            name="notification_loop"
        )

        # Start source monitoring tasks
        await self._refresh_source_tasks()

        # Periodically refresh source list
        asyncio.create_task(self._source_refresh_loop(), name="source_refresh")

        # Proactive live event URL discovery (runs every 5 minutes)
        asyncio.create_task(self._proactive_probe_loop(), name="proactive_probe")

        logger.info("Monitoring scheduler started")

    async def stop(self):
        """Stop the monitoring scheduler."""
        self._running = False
        logger.info("Stopping monitoring scheduler...")

        for source_id, task in self._tasks.items():
            task.cancel()
        self._tasks.clear()

        if self._notification_task:
            self._notification_task.cancel()

        logger.info("Monitoring scheduler stopped")

    async def _refresh_source_tasks(self):
        """Refresh monitoring tasks based on active sources."""
        try:
            sources = await get_all_sources(active_only=True)
            active_ids = {s["id"] for s in sources}

            # Cancel tasks for removed/disabled sources
            for source_id in list(self._tasks.keys()):
                if source_id not in active_ids:
                    self._tasks[source_id].cancel()
                    del self._tasks[source_id]

            # Start tasks for new sources
            for source in sources:
                source_id = source["id"]
                if source_id not in self._tasks or self._tasks[source_id].done():
                    interval = source["check_interval_seconds"]
                    self._tasks[source_id] = asyncio.create_task(
                        self._source_monitor_loop(source_id, source["name"], interval),
                        name=f"monitor_{source['name']}"
                    )
                    logger.info(f"Started monitor for {source['name']} (every {interval}s)")

        except Exception as e:
            logger.error(f"Error refreshing source tasks: {e}")

    async def _source_monitor_loop(self, source_id: int, source_name: str, interval: int):
        """Monitor a single source at the specified interval."""
        logger.info(f"Starting monitor loop for {source_name} (interval: {interval}s)")

        # Initial delay to stagger checks
        await asyncio.sleep(source_id % 10)

        while self._running:
            try:
                result = await check_source(source_id)
                self._check_count += 1
                self._last_check_results[source_id] = {
                    "source": source_name,
                    "checked_at": datetime.utcnow().isoformat(),
                    "has_changes": result.get("has_changes", False),
                    "summary": result.get("summary", ""),
                    "error": result.get("error"),
                    "detections_count": len(result.get("detections", []))
                }

                if result.get("has_changes"):
                    logger.info(
                        f"[{source_name}] Changes found: {result.get('summary', '')}"
                    )

            except asyncio.CancelledError:
                logger.info(f"Monitor for {source_name} cancelled")
                break
            except Exception as e:
                logger.error(f"Error monitoring {source_name}: {e}")
                self._last_check_results[source_id] = {
                    "source": source_name,
                    "checked_at": datetime.utcnow().isoformat(),
                    "error": str(e)
                }

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def _notification_loop(self):
        """Periodically process the notification queue."""
        while self._running:
            try:
                await process_notification_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Notification processing error: {e}")

            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break

    async def _source_refresh_loop(self):
        """Periodically refresh the list of monitored sources."""
        while self._running:
            try:
                await asyncio.sleep(60)
                await self._refresh_source_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Source refresh error: {e}")

    async def _proactive_probe_loop(self):
        """Periodically probe for new live event/campaign URLs using Firecrawl map, sitemap, etc.
        
        This catches JS-rendered content and pages not linked in static HTML.
        Runs every 5 minutes.
        """
        # Initial delay to let other tasks start first
        await asyncio.sleep(30)
        while self._running:
            try:
                logger.info("Running proactive live event URL probe...")
                discovered = await probe_live_event_urls()
                if discovered:
                    await _auto_register_discovered_sources(discovered, "proactive_probe")
                    logger.info(f"Proactive probe: processed {len(discovered)} discovered URLs")
                else:
                    logger.info("Proactive probe: no new URLs discovered")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Proactive probe error: {e}")

            try:
                await asyncio.sleep(300)  # Every 5 minutes
            except asyncio.CancelledError:
                break

    async def trigger_check(self, source_id: int) -> dict:
        """Manually trigger a check for a specific source."""
        result = await check_source(source_id)
        self._check_count += 1
        return result

    async def trigger_check_all(self) -> list:
        """Manually trigger a check for all active sources."""
        sources = await get_all_sources(active_only=True)
        results = []
        for source in sources:
            result = await check_source(source["id"])
            self._check_count += 1
            results.append(result)
            await asyncio.sleep(1)
        return results


# Global scheduler instance
scheduler = MonitorScheduler()
