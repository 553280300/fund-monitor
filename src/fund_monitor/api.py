"""Loopback API for the local management panel."""

from __future__ import annotations

import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fund_monitor.domain import AlertRule, Asset, AssetCandidate, ChannelConfig, NotificationMessage
from fund_monitor.storage import Database
from fund_monitor.monitoring import MonitoringService
from fund_monitor.scheduler import MonitorScheduler
from fund_monitor.secrets import SecretStore
from fund_monitor.providers.search import EastmoneySearchProvider
from fund_monitor.report import build_report, render_text
from fund_monitor.notifications.configured import ChannelFactory
from fund_monitor import ghconfig

DEFAULT_SCHEDULE_TIMES = ["02:00", "06:00", "10:00", "14:00"]


class SecretInput(BaseModel):
    secret: str = Field(min_length=1, max_length=4096)


class GhSyncInput(BaseModel):
    repo: str = Field(default=ghconfig.REPO, min_length=1, max_length=200)


def create_app(
    database: Database,
    *,
    monitor: MonitoringService | None = None,
    scheduler: MonitorScheduler | None = None,
    secret_store: SecretStore | None = None,
    search: EastmoneySearchProvider | None = None,
    schedule_times: list[str] | None = None,
    timezone_name: str = "Asia/Shanghai",
) -> FastAPI:
    secret_store = secret_store or SecretStore()
    search = search or EastmoneySearchProvider()
    schedule_times = schedule_times or DEFAULT_SCHEDULE_TIMES
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if scheduler is not None:
            await scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                await scheduler.stop()

    app = FastAPI(title="Fund Monitor", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    module_path = Path(__file__).resolve()
    web_candidates = [module_path.parents[1] / "web", module_path.parents[2] / "web"]
    web_root = next((candidate for candidate in web_candidates if candidate.is_dir()), web_candidates[-1])
    app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="assets")

    def get_database() -> Database:
        return database

    @app.get("/", include_in_schema=False)
    async def panel() -> FileResponse:
        return FileResponse(web_root / "index.html")

    @app.get("/api/health")
    async def health(db: Database = Depends(get_database)) -> dict:
        components = db.health.list()
        degraded = any(component["status"] != "healthy" for component in components)
        return {"status": "degraded" if degraded else "healthy", "components": components}

    @app.get("/api/v1/search", response_model=list[AssetCandidate])
    async def search_assets(q: str = Query(min_length=1, max_length=60)) -> list[AssetCandidate]:
        candidates = await search.search(q)
        return [candidate.model_copy(update={"identifiers": candidate.to_identifiers()}) for candidate in candidates]

    @app.post("/api/v1/monitor/run")
    async def run_monitor(db: Database = Depends(get_database)) -> dict:
        if monitor is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Monitoring service is unavailable")
        run = await monitor.run_once()
        report = build_report(run, schedule_times=schedule_times, timezone_name=timezone_name)
        text = render_text(report)
        db.runs.save(
            ran_at=run.ran_at.isoformat(),
            period=report["period"],
            report_json=json.dumps(report, ensure_ascii=False),
            report_text=text,
        )
        return {"report": report, "text": text}

    @app.get("/api/v1/monitor/runs")
    async def recent_runs(limit: int = Query(default=10, ge=1, le=50), db: Database = Depends(get_database)) -> list[dict]:
        return db.runs.recent(limit=limit)

    @app.get("/api/v1/monitor/status")
    async def monitor_status() -> dict:
        if scheduler is None:
            return {"running": False, "schedule_times": schedule_times, "next_due_at": None}
        status_info = scheduler.status()
        return {
            "running": status_info.running,
            "schedule_times": list(status_info.schedule_times or schedule_times),
            "next_due_at": status_info.next_due_at.isoformat() if status_info.next_due_at else None,
            "last_started_at": status_info.last_started_at.isoformat() if status_info.last_started_at else None,
            "last_finished_at": status_info.last_finished_at.isoformat() if status_info.last_finished_at else None,
            "last_error": status_info.last_error,
        }

    @app.get("/api/v1/assets", response_model=list[Asset])
    async def list_assets(db: Database = Depends(get_database)) -> list[Asset]:
        return db.assets.list()

    @app.get("/api/v1/assets/overview")
    async def assets_overview(db: Database = Depends(get_database)) -> list[dict]:
        """Assets with their most recent observation, for the panel dashboard."""
        overview: list[dict] = []
        for asset in db.assets.list(enabled_only=True):
            latest = db.observations.latest_for_asset(asset.id or 0)
            overview.append(
                {
                    "id": asset.id,
                    "name": asset.name,
                    "code": next(iter(asset.identifiers.values()), ""),
                    "kind": asset.kind.value,
                    "value": str(latest.value) if latest and latest.value is not None else None,
                    "change_percent": (
                        str(latest.change_percent) if latest and latest.change_percent is not None else None
                    ),
                    "observed_at": latest.observed_at.isoformat() if latest else None,
                    "source": latest.source if latest else None,
                }
            )
        return overview

    @app.post("/api/v1/assets", response_model=Asset, status_code=status.HTTP_201_CREATED)
    async def create_asset(asset: Asset, db: Database = Depends(get_database)) -> Asset:
        if asset.id is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="id is assigned by the service")
        return db.assets.create(asset)

    @app.get("/api/v1/assets/{asset_id}", response_model=Asset)
    async def get_asset(asset_id: int, db: Database = Depends(get_database)) -> Asset:
        asset = db.assets.get(asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        return asset

    @app.post("/api/v1/assets/{asset_id}/check")
    async def check_asset(asset_id: int, db: Database = Depends(get_database)) -> dict:
        if db.assets.get(asset_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        if monitor is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Monitoring service is unavailable")
        summary = await monitor.check_asset(asset_id)
        return {
            "asset_id": summary.asset_id,
            "alerts_created": summary.alerts_created,
            "source": summary.source,
            "error": summary.error,
        }

    @app.put("/api/v1/assets/{asset_id}", response_model=Asset)
    async def update_asset(asset_id: int, asset: Asset, db: Database = Depends(get_database)) -> Asset:
        updated = db.assets.update(asset_id, asset)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        return updated

    @app.delete("/api/v1/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_asset(asset_id: int, db: Database = Depends(get_database)) -> Response:
        if not db.assets.delete(asset_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/v1/assets/{asset_id}/rules", response_model=list[AlertRule])
    async def list_rules(asset_id: int, db: Database = Depends(get_database)) -> list[AlertRule]:
        if db.assets.get(asset_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        return db.rules.for_asset(asset_id, enabled_only=False)

    @app.post("/api/v1/assets/{asset_id}/rules", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
    async def create_rule(asset_id: int, rule: AlertRule, db: Database = Depends(get_database)) -> AlertRule:
        if db.assets.get(asset_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        if rule.asset_id != asset_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Rule asset_id must match the URL")
        if rule.id is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="id is assigned by the service")
        return db.rules.create(rule)

    @app.get("/api/v1/channels", response_model=list[ChannelConfig])
    async def list_channels(db: Database = Depends(get_database)) -> list[ChannelConfig]:
        return db.channels.list()

    @app.post("/api/v1/channels", response_model=ChannelConfig, status_code=status.HTTP_201_CREATED)
    async def create_channel(channel: ChannelConfig, db: Database = Depends(get_database)) -> ChannelConfig:
        if channel.id is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="id is assigned by the service")
        return db.channels.create(channel)

    @app.put("/api/v1/channels/{channel_id}/secret", status_code=status.HTTP_204_NO_CONTENT)
    async def set_channel_secret(channel_id: int, payload: SecretInput, db: Database = Depends(get_database)) -> Response:
        if db.channels.get(channel_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        secret_store.set(f"channel:{channel_id}", payload.secret)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.delete("/api/v1/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_channel(channel_id: int, db: Database = Depends(get_database)) -> Response:
        if not db.channels.delete(channel_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        secret_store.delete(f"channel:{channel_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/v1/channels/{channel_id}/test")
    async def test_channel(channel_id: int, db: Database = Depends(get_database)) -> dict:
        config = db.channels.get(channel_id)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        try:
            channel = ChannelFactory(secret_store)(config)
        except Exception as exc:
            return {"ok": False, "detail": f"通道配置不完整：{exc}"}
        message = NotificationMessage(
            title="基金监控测试通知",
            body="这是一条测试消息，收到说明通道配置正确。",
        )
        try:
            await channel.send(message)
        except Exception as exc:
            return {"ok": False, "detail": str(exc) or "发送失败"}
        return {"ok": True, "detail": "发送成功"}

    @app.get("/api/v1/ghconfig")
    async def get_gh_config(db: Database = Depends(get_database)) -> dict:
        content = ghconfig.build_config(db)
        return {"content": content, "repo": ghconfig.REPO}

    @app.put("/api/v1/ghconfig/token", status_code=status.HTTP_204_NO_CONTENT)
    async def save_gh_token(payload: SecretInput) -> Response:
        secret_store.set("github:token", payload.secret)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.delete("/api/v1/ghconfig/token", status_code=status.HTTP_204_NO_CONTENT)
    async def clear_gh_token() -> Response:
        secret_store.delete("github:token")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/v1/ghconfig/sync")
    async def sync_gh_config(payload: GhSyncInput | None = None, db: Database = Depends(get_database)) -> dict:
        repo = (payload.repo if payload else None) or ghconfig.REPO
        token = secret_store.get("github:token")
        try:
            content = ghconfig.build_config(db)
            message = ghconfig.sync_config(content, repo=repo, token=token)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        return {"ok": True, "detail": message}

    @app.get("/api/v1/config/export")
    async def export_configuration(db: Database = Depends(get_database)) -> dict:
        return {
            "assets": [asset.model_dump(mode="json") for asset in db.assets.list()],
            "rules": [
                rule.model_dump(mode="json")
                for asset in db.assets.list()
                for rule in db.rules.for_asset(asset.id or 0, enabled_only=False)
            ],
            "channels": [channel.model_dump(mode="json") for channel in db.channels.list()],
        }

    return app
