from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cross_platform_sync import CONFIG_PATH, load_settings, run_pipeline, validate_settings

app = FastAPI(title="Cross-Platform Sync API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STEP_ORDER = ["step1", "step2", "step3", "step4", "step5", "done"]


class RunRequest(BaseModel):
    config_path: str = CONFIG_PATH


state_lock = threading.Lock()
state: dict[str, Any] = {
    "current_run": None,
    "history": [],
}


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _append_log(run: dict[str, Any], level: str, message: str, step: str | None) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{timestamp}] {level.upper()}"
    if step:
        prefix += f" [{step}]"
    run["logs"].append(f"{prefix} {message}")


def _event_callback(level: str, message: str, step: str | None, payload: dict[str, Any] | None) -> None:
    with state_lock:
        current = state["current_run"]
        if not current:
            return
        _append_log(current, level, message, step)
        if step:
            current["active_step"] = step
        if payload:
            current["summary"] = payload


def _run_pipeline_in_background(config_path: str, run_id: str) -> None:
    try:
        summary = run_pipeline(config_path=config_path, emit=_event_callback)
        with state_lock:
            current = state["current_run"]
            if not current or current["run_id"] != run_id:
                return
            current["status"] = "completed"
            current["summary"] = summary
            current["finished_at"] = _utc_now()
            state["history"] = [deepcopy(current), *state["history"]][:10]
    except Exception as ex:
        with state_lock:
            current = state["current_run"]
            if not current or current["run_id"] != run_id:
                return
            current["status"] = "failed"
            current["error"] = str(ex)
            current["finished_at"] = _utc_now()
            _append_log(current, "error", str(ex), current.get("active_step"))
            state["history"] = [deepcopy(current), *state["history"]][:10]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/config/validate")
def validate_config(request: RunRequest) -> dict[str, Any]:
    settings = load_settings(request.config_path)
    missing = validate_settings(settings)
    return {
        "ok": len(missing) == 0,
        "config_path": request.config_path,
        "missing": missing,
    }


@app.post("/api/sync/run")
def start_sync(request: RunRequest) -> dict[str, Any]:
    with state_lock:
        current = state["current_run"]
        if current and current["status"] == "running":
            raise HTTPException(status_code=409, detail="A sync run is already in progress.")

        run_id = str(uuid.uuid4())
        state["current_run"] = {
            "run_id": run_id,
            "status": "running",
            "config_path": request.config_path,
            "started_at": _utc_now(),
            "finished_at": None,
            "active_step": "init",
            "logs": [],
            "summary": None,
            "error": None,
        }

        worker = threading.Thread(
            target=_run_pipeline_in_background,
            args=(request.config_path, run_id),
            daemon=True,
        )
        worker.start()

        return deepcopy(state["current_run"])


@app.get("/api/sync/status")
def sync_status() -> dict[str, Any]:
    with state_lock:
        return {
            "current_run": deepcopy(state["current_run"]),
            "history": deepcopy(state["history"]),
            "step_order": STEP_ORDER,
        }
