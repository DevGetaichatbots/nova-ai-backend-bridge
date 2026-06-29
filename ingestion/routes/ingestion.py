"""
NUSF V2 Ingestion Routes
=========================
FastAPI router for /v2/ endpoints. ZERO imports from src/.

All downstream dependencies (vector_store_manager, save_session_metadata,
predictive_agent, format_predictive_as_html) are injected at configuration
time via configure() before the router is mounted. This keeps ingestion/
fully self-contained.

Wire-up in src/main.py:
    from ingestion.routes.ingestion import router as _v2_router, configure as _v2_configure
    from ingestion.routes.ingestion import RouterDependencies
    _v2_configure(RouterDependencies(
        vector_store_manager=...,
        save_session_metadata=...,
        predictive_agent=...,
        format_html=...,
    ))
    app.include_router(_v2_router, prefix="/v2")

Endpoints:
  GET    /v2/health                          — pipeline health check
  POST   /v2/inspect                         — diagnose a file through the pipeline
  POST   /v2/upload                          — two-schedule comparison upload
  GET    /v2/upload/progress/{upload_id}     — poll upload progress
  POST   /v2/predictive                      — single-schedule Nova Insight analysis
  GET    /v2/predictive/progress/{analysis_id} — poll predictive progress
"""
from __future__ import annotations
import asyncio
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ingestion.pipeline import IngestionPipeline, PipelineError
from ingestion.normalization.engine import to_nusf_chunks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["v2-nusf"])

_executor = ThreadPoolExecutor(max_workers=4)
_pipeline = IngestionPipeline()

_v2_upload_progress: Dict[str, Dict[str, Any]] = {}
_v2_predictive_progress: Dict[str, Dict[str, Any]] = {}
_progress_lock = threading.Lock()

_ALLOWED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".mpp", ".xml"}


@dataclass
class RouterDependencies:
    """
    Downstream dependencies injected from src/ at mount time.
    Keeps ingestion/ free of src/ imports.
    """
    vector_store_manager: Any
    save_session_metadata: Callable
    predictive_agent: Any
    format_html: Callable
    rag_agent: Any = None
    format_comparison_html: Callable = None
    get_session_metadata: Callable = None


_deps: Optional[RouterDependencies] = None


def configure(deps: RouterDependencies) -> None:
    """Call this once from src/main.py before including the router."""
    global _deps
    _deps = deps
    logger.info("V2 router dependencies configured")


def _require_deps() -> RouterDependencies:
    if _deps is None:
        raise RuntimeError(
            "V2 router dependencies not configured. "
            "Call ingestion.routes.ingestion.configure(RouterDependencies(...)) "
            "before mounting the router."
        )
    return _deps


def _is_allowed(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in _ALLOWED_EXTENSIONS)


def _schedule_cleanup(store: Dict, key: str, delay: int = 300):
    def _clean():
        time.sleep(delay)
        store.pop(key, None)
    threading.Thread(target=_clean, daemon=True).start()


def _extract_ref_date(name: str) -> Optional[str]:
    patterns = [
        (r"(\d{4})-(\d{2})-(\d{2})", lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (r"(\d{2})-(\d{2})-(\d{4})", lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
        (r"(\d{2})\.(\d{2})\.(\d{4})", lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
        (r"(\d{4})(\d{2})(\d{2})", lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    ]
    for pattern, parser in patterns:
        m = re.search(pattern, name)
        if m:
            try:
                return parser(m).strftime("%d-%m-%Y")
            except ValueError:
                continue
    return None


def _issues_to_list(issues: list) -> list:
    return [
        {
            "level": i.level,
            "category": i.category,
            "activity_id": i.activity_id,
            "message": i.message,
            "remediation": i.remediation,
        }
        for i in issues
    ]


@router.get("/health")
async def v2_health():
    from ingestion.extractors.registry import ExtractorRegistry
    return {
        "status": "healthy",
        "pipeline": "NUSF v1.0",
        "registered_extractors": ExtractorRegistry.available(),
        "dependencies_configured": _deps is not None,
    }


@router.post("/inspect")
async def v2_inspect_file(schedule: UploadFile = File(...)):
    """
    Debug endpoint: run a file through the NUSF pipeline and return
    the NormalizedSchedule metadata + validation issues without
    storing anything in the vector database.
    """
    filename = schedule.filename or "schedule.pdf"
    if not _is_allowed(filename):
        raise HTTPException(status_code=400, detail="Only PDF, CSV, Excel (.xlsx), Microsoft Project (.mpp), and MS Project XML (.xml) files are accepted")

    file_bytes = await schedule.read()
    loop = asyncio.get_event_loop()

    try:
        schedule_obj, chunks = await loop.run_in_executor(
            _executor,
            lambda: _pipeline.run_from_bytes(file_bytes, filename),
        )
    except PipelineError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": str(e),
                "issues": _issues_to_list(e.issues),
            },
        )
    except Exception as e:
        logger.exception(f"[v2/inspect] Unexpected error processing '{filename}': {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"{type(e).__name__}: {str(e)}"},
        )

    meta = schedule_obj.metadata
    return {
        "pipeline": "NUSF",
        "validation_passed": schedule_obj.validation_passed,
        "filename": meta.source_filename,
        "source_system": meta.source_system,
        "total_activities": meta.total_activities,
        "total_relationships": meta.total_relationships,
        "parse_quality_score": meta.parse_quality_score,
        "parse_duration_seconds": meta.parse_duration_seconds,
        "earliest_date": meta.earliest_date.isoformat(),
        "latest_date": meta.latest_date.isoformat(),
        "duration_days": meta.duration_days,
        "compact_chunks": len(chunks),
        "validation_issues": _issues_to_list(schedule_obj.validation_issues),
        "sample_activities": [
            {
                "source_id": a.source_id,
                "name": a.name[:80],
                "planned_start": a.planned_start.strftime("%d-%m-%Y"),
                "planned_finish": a.planned_finish.strftime("%d-%m-%Y"),
                "percent_complete": a.percent_complete,
                "activity_type": a.activity_type.value,
                "discipline": a.discipline,
            }
            for a in schedule_obj.activities[:10]
        ],
    }


@router.post("/upload")
async def v2_upload_schedules(
    session_id: str = Form(...),
    old_session_id: str = Form(...),
    new_session_id: str = Form(...),
    old_schedule: UploadFile = File(...),
    new_schedule: UploadFile = File(...),
):
    """
    Upload two schedule files through the NUSF pipeline for comparison analysis.
    Returns upload_id for progress polling.
    """
    old_filename = old_schedule.filename or "old_schedule.pdf"
    new_filename = new_schedule.filename or "new_schedule.pdf"

    if not _is_allowed(old_filename) or not _is_allowed(new_filename):
        raise HTTPException(status_code=400, detail="Only PDF, CSV, Excel (.xlsx), Microsoft Project (.mpp), and MS Project XML (.xml) files are accepted")

    old_bytes = await old_schedule.read()
    new_bytes = await new_schedule.read()

    upload_id = str(uuid.uuid4())[:8]

    with _progress_lock:
        _v2_upload_progress[upload_id] = {
            "status": "processing",
            "upload_id": upload_id,
            "session_id": session_id,
            "old_filename": old_filename,
            "new_filename": new_filename,
            "pipeline": "NUSF",
            "started_at": time.time(),
            "old_schedule": {"step": "queued", "detail": "Waiting to start", "progress": 0},
            "new_schedule": {"step": "queued", "detail": "Waiting to start", "progress": 0},
            "overall_progress": 0,
        }

    loop = asyncio.get_event_loop()

    def _update_upload(key: str, **kwargs):
        with _progress_lock:
            if upload_id not in _v2_upload_progress:
                return
            if key in _v2_upload_progress[upload_id] and isinstance(_v2_upload_progress[upload_id][key], dict):
                _v2_upload_progress[upload_id][key].update(kwargs)
            else:
                _v2_upload_progress[upload_id].update(kwargs)
            old_pct = _v2_upload_progress[upload_id].get("old_schedule", {}).get("progress", 0)
            new_pct = _v2_upload_progress[upload_id].get("new_schedule", {}).get("progress", 0)
            _v2_upload_progress[upload_id]["overall_progress"] = (old_pct + new_pct) // 2

    async def _background():
        try:
            deps = _require_deps()

            def _process_one(file_key: str, filename: str, file_bytes: bytes, table_id: str):
                _update_upload(file_key, step="pipeline", detail=f"Running NUSF pipeline on {filename}...", progress=15)
                try:
                    schedule_obj, raw_chunks = _pipeline.run_from_bytes(file_bytes, filename)
                except PipelineError as e:
                    logger.error(f"[v2/upload] Pipeline error for {filename}: {e}")
                    _update_upload(
                        file_key,
                        step="error",
                        detail=str(e),
                        progress=0,
                        validation_issues=_issues_to_list(e.issues),
                    )
                    with _progress_lock:
                        _v2_upload_progress[upload_id]["status"] = "error"
                        _v2_upload_progress[upload_id]["error"] = str(e)
                        _v2_upload_progress[upload_id]["validation_issues"] = _issues_to_list(e.issues)
                    raise
                except Exception as e:
                    logger.exception(f"[v2/upload] Unexpected error for {filename}: {type(e).__name__}: {e}")
                    _update_upload(
                        file_key,
                        step="error",
                        detail=f"{type(e).__name__}: {str(e)}",
                        progress=0,
                    )
                    with _progress_lock:
                        _v2_upload_progress[upload_id]["status"] = "error"
                        _v2_upload_progress[upload_id]["error"] = f"{type(e).__name__}: {str(e)}"
                    raise

                chunks = to_nusf_chunks(schedule_obj) if schedule_obj.activities else raw_chunks
                warnings = [i for i in schedule_obj.validation_issues if i.level != "ERROR"]
                _update_upload(file_key, step="storing", detail=f"Storing {len(chunks)} chunks...", progress=60)

                result = deps.vector_store_manager.create_store_from_chunks(
                    session_id, filename, chunks, table_id
                )

                _update_upload(file_key, **{
                    "step": "complete",
                    "detail": f"{result.get('chunks_processed', 0)} chunks stored, {len(warnings)} warnings",
                    "progress": 100,
                    "table_name": result.get("table_name"),
                    "chunks": result.get("chunks_processed", 0),
                    "nusf_activities": schedule_obj.metadata.total_activities,
                    "nusf_quality": schedule_obj.metadata.parse_quality_score,
                    "nusf_format": schedule_obj.metadata.source_system,
                    "nusf_warnings": len(warnings),
                    "validation_issues": _issues_to_list(warnings),
                })
                return result

            old_f = loop.run_in_executor(_executor, lambda: _process_one("old_schedule", old_filename, old_bytes, old_session_id))
            new_f = loop.run_in_executor(_executor, lambda: _process_one("new_schedule", new_filename, new_bytes, new_session_id))

            old_result, new_result = await asyncio.gather(old_f, new_f)
            deps.save_session_metadata(
                session_id,
                old_filename,
                new_filename,
                old_session_id,
                new_session_id,
                data_format="nusf",
            )

            elapsed = time.time() - _v2_upload_progress[upload_id]["started_at"]
            with _progress_lock:
                _v2_upload_progress[upload_id].update(
                    status="complete",
                    overall_progress=100,
                    elapsed_seconds=round(elapsed, 1),
                )
            logger.info(f"[v2/upload] Complete ({elapsed:.1f}s) upload_id={upload_id}")

        except Exception as e:
            logger.error(f"[v2/upload] Failed: {e}")
            with _progress_lock:
                _v2_upload_progress.setdefault(upload_id, {}).update(
                    status="error", error=str(e)
                )

    asyncio.create_task(_background())
    _schedule_cleanup(_v2_upload_progress, upload_id, 600)

    return {
        "status": "processing",
        "upload_id": upload_id,
        "session_id": session_id,
        "pipeline": "NUSF",
        "message": f"Upload started. Poll GET /v2/upload/progress/{upload_id} for progress.",
    }


@router.get("/upload/progress/{upload_id}")
async def v2_get_upload_progress(upload_id: str):
    with _progress_lock:
        progress = _v2_upload_progress.get(upload_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Upload ID not found")
    return progress


@router.post("/predictive")
async def v2_predictive_analysis(
    schedule: UploadFile = File(...),
    language: str = Form("en"),
    format: str = Form("html"),
    analysis_id: str = Form(None),
):
    """
    Upload a single schedule through the NUSF pipeline for Nova Insight predictive analysis.
    Supports PDF, CSV, and Excel (.xlsx). Returns analysis_id for progress polling.
    """
    if not analysis_id:
        analysis_id = str(uuid.uuid4())[:12]

    filename = schedule.filename or "schedule.pdf"
    filename_clean = filename.rsplit(".", 1)[0]

    if not _is_allowed(filename):
        raise HTTPException(status_code=400, detail="Only PDF, CSV, Excel (.xlsx), Microsoft Project (.mpp), and MS Project XML (.xml) files are accepted")

    file_bytes = await schedule.read()
    reference_date = _extract_ref_date(filename_clean)

    with _progress_lock:
        _v2_predictive_progress[analysis_id] = {
            "analysis_id": analysis_id,
            "stage": "received",
            "step": 1,
            "total_steps": 6,
            "message": "Received — starting NUSF pipeline...",
            "timestamp": time.time(),
        }

    loop = asyncio.get_event_loop()
    start_time = time.time()

    def _set_progress(stage: str, message: str, step: int, detail: str = None):
        with _progress_lock:
            _v2_predictive_progress[analysis_id].update(
                stage=stage, message=message, step=step,
                timestamp=time.time(), detail=detail,
            )

    async def _background():
        try:
            deps = _require_deps()

            _set_progress("pipeline", "Running NUSF ingestion pipeline...", 2)
            try:
                schedule_obj, raw_chunks = await loop.run_in_executor(
                    _executor,
                    lambda: _pipeline.run_from_bytes(file_bytes, filename),
                )
            except PipelineError as e:
                logger.error(f"[v2/predictive] Pipeline error: {e}")
                with _progress_lock:
                    _v2_predictive_progress[analysis_id].update(
                        stage="error",
                        step=-1,
                        message=str(e),
                        error=str(e),
                        validation_issues=_issues_to_list(e.issues),
                        timestamp=time.time(),
                    )
                _schedule_cleanup(_v2_predictive_progress, analysis_id, 120)
                return
            except Exception as e:
                logger.exception(f"[v2/predictive] Unexpected error: {type(e).__name__}: {e}")
                with _progress_lock:
                    _v2_predictive_progress[analysis_id].update(
                        stage="error",
                        step=-1,
                        message=f"{type(e).__name__}: {str(e)}",
                        error=f"{type(e).__name__}: {str(e)}",
                        timestamp=time.time(),
                    )
                _schedule_cleanup(_v2_predictive_progress, analysis_id, 120)
                return

            chunks = to_nusf_chunks(schedule_obj) if schedule_obj.activities else raw_chunks
            warnings = [i for i in schedule_obj.validation_issues if i.level != "ERROR"]
            row_count = schedule_obj.metadata.total_activities
            logger.info(
                f"[v2/predictive] Pipeline complete: {row_count} activities, "
                f"{len(chunks)} chunks, {len(warnings)} warnings"
            )

            _set_progress(
                "extracting",
                f"Found {row_count} activities via NUSF ({schedule_obj.metadata.source_system})",
                3,
                detail=f"{row_count} activities",
            )

            MAX_CONTEXT_BYTES = 1_900_000
            table_chunks = [c for c in chunks if c.get("metadata", {}).get("type") == "table"]
            preamble = f"[{filename_clean}] — COMPLETE SCHEDULE DATA\nScan EVERY row for delayed activities.\n\n"
            budget = MAX_CONTEXT_BYTES - len(preamble.encode("utf-8"))
            included_parts: list = []
            current_bytes = 0
            for chunk in table_chunks:
                cb = len(chunk["content"].encode("utf-8")) + 1
                if current_bytes + cb > budget:
                    break
                included_parts.append(chunk["content"])
                current_bytes += cb
            context = preamble + "\n".join(included_parts) + "\n"

            _set_progress("analyzing", "Nova Insight is analyzing your schedule...", 4)

            predictive_result = await loop.run_in_executor(
                _executor,
                lambda: deps.predictive_agent.analyze(
                    context=context,
                    user_query=(
                        "Execute full two-phase analysis: detect ALL delayed activities "
                        "(Phase 1) and produce decision support with root cause analysis, "
                        "priority ranking, action recommendations, and resource assessment (Phase 2)"
                    ),
                    language=language,
                    schedule_filename=filename_clean,
                    reference_date=reference_date,
                    data_format="nusf",
                ),
            )

            predictive_json = predictive_result.get("predictive_json")
            predictive_text = predictive_result.get("predictive_insights", "")
            predictive_status = predictive_result.get("status", "error")

            _set_progress("formatting", "Building report...", 5)

            if format == "html" and predictive_json:
                predictive_text = deps.format_html(predictive_json, language)
            elif format == "html" and predictive_text:
                predictive_text = deps.format_html(predictive_text, language)

            elapsed = time.time() - start_time

            with _progress_lock:
                _v2_predictive_progress[analysis_id] = {
                    "analysis_id": analysis_id,
                    "stage": "complete",
                    "step": 6,
                    "total_steps": 6,
                    "message": "Analysis ready",
                    "timestamp": time.time(),
                    "validation_issues": _issues_to_list(warnings),
                    "result": {
                        "predictive_insights": predictive_text,
                        "predictive_status": predictive_status,
                        "filename": filename,
                        "reference_date": reference_date,
                        "format": format,
                        "processing_time_seconds": round(elapsed, 1),
                        "pipeline": "NUSF",
                        "nusf_activities": row_count,
                        "nusf_quality": schedule_obj.metadata.parse_quality_score,
                        "nusf_format": schedule_obj.metadata.source_system,
                        "nusf_warnings": len(warnings),
                    },
                }

            _schedule_cleanup(_v2_predictive_progress, analysis_id, 300)
            logger.info(f"[v2/predictive] Complete ({elapsed:.1f}s) analysis_id={analysis_id}")

        except Exception as e:
            logger.error(f"[v2/predictive] Unexpected error: {e}", exc_info=True)
            with _progress_lock:
                _v2_predictive_progress[analysis_id].update(
                    stage="error", step=-1, message=str(e),
                    error=str(e), timestamp=time.time(),
                )
            _schedule_cleanup(_v2_predictive_progress, analysis_id, 120)

    asyncio.create_task(_background())

    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "pipeline": "NUSF",
        "message": f"Analysis started. Poll GET /v2/predictive/progress/{analysis_id} for progress.",
    }


@router.get("/predictive/progress/{analysis_id}")
async def v2_get_predictive_progress(analysis_id: str):
    with _progress_lock:
        progress = _v2_predictive_progress.get(analysis_id)
    if not progress:
        raise HTTPException(
            status_code=404,
            detail="No analysis found with this ID. It may have completed or expired.",
        )
    return progress


@router.post("/query")
async def v2_query_agent(
    query: str = Form(...),
    vs_table: str = Form(...),
    old_session_id: str = Form(...),
    new_session_id: str = Form(...),
    language: str = Form("en"),
    format: str = Form("html"),
):
    """
    Comparison query for v2 (NUSF) sessions. Identical params to POST /query
    but always passes data_format="nusf" to the agent — no auto-detection needed.
    """
    deps = _require_deps()
    if deps.rag_agent is None or deps.get_session_metadata is None:
        raise HTTPException(status_code=503, detail="v2/query: rag_agent not configured")

    logger.info(f"=== V2 QUERY REQUEST === session={vs_table} lang={language}")

    loop = asyncio.get_event_loop()

    session_meta = deps.get_session_metadata(vs_table)
    old_filename = session_meta.get("old_filename", "Old Schedule")
    new_filename = session_meta.get("new_filename", "New Schedule")
    old_filename_clean = old_filename.replace(".pdf", "").replace(".PDF", "")
    new_filename_clean = new_filename.replace(".pdf", "").replace(".PDF", "")
    logger.info(f"  Files: {old_filename} / {new_filename} | data_format=nusf")

    result = await loop.run_in_executor(
        _executor,
        lambda: deps.rag_agent.query(
            user_query=query,
            table_names=[old_session_id, new_session_id],
            session_id=vs_table,
            language=language,
            top_k=10,
            old_filename=old_filename_clean,
            new_filename=new_filename_clean,
            data_format="nusf",
        ),
    )

    response_text = result["response"]

    import re as _re
    _STRUCTURED_MARKERS = [
        r"^##\s*EXECUTIVE_TOP", r"^##\s*LEDELSESOVERBLIK",
        r"^##\s*BIGGEST_RISK", r"^##\s*STØRSTE_RISIKO",
        r"^##\s*ESTIMATED_IMPACT", r"^##\s*ESTIMERET_KONSEKVENS",
        r"^##\s*CONFIDENCE_LEVEL", r"^##\s*TILLIDSNIVEAU",
        r"^##\s*ROOT_CAUSE_ANALYSIS", r"^##\s*ÅRSAGSANALYSE",
        r"^##\s*RECOMMENDED_ACTIONS", r"^##\s*ANBEFALEDE_HANDLINGER",
        r"^##\s*EXECUTIVE_ACTIONS", r"^##\s*HANDLINGSPLAN",
        r"^##\s*SUMMARY_OF_CHANGES", r"^##\s*OPSUMMERING_AF_ÆNDRINGER",
        r"^##\s*PROJECT_HEALTH", r"^##\s*PROJEKTSUNDHED",
        r"^##\s*COMPARISON", r"^##\s*IMPACT_ASSESSMENT",
        r"^##\s*DATA_TRUST", r"^##\s*DATAGRUNDLAG",
        r"<!--DECISION_ENGINE:", r"<!--HEALTH_DATA:",
    ]
    has_sections = any(
        _re.search(p, response_text, _re.MULTILINE | _re.IGNORECASE)
        for p in _STRUCTURED_MARKERS
    )

    if format == "html" and has_sections and deps.format_comparison_html:
        response_text = deps.format_comparison_html(
            response_text,
            language,
            total_data_rows=result.get("total_data_rows", 0),
            diff_data=result.get("diff_data"),
        )
    elif format == "html":
        from html import escape as _html_escape
        conv = _html_escape(response_text)
        conv = _re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', conv)
        conv = _re.sub(r'\*([^*]+)\*', r'<em>\1</em>', conv)
        lines = conv.split('\n')
        html_lines = []
        in_list = False
        for ln in lines:
            stripped = ln.strip()
            if stripped.startswith('- ') or stripped.startswith('&bull; ') or stripped.startswith('• ') or stripped.startswith('* '):
                if not in_list:
                    html_lines.append('<ul style="margin:8px 0;padding-left:20px;">')
                    in_list = True
                item_text = _re.sub(r'^[-•*]\s*|^&bull;\s*', '', stripped)
                html_lines.append(f'<li style="margin:4px 0;line-height:1.6;">{item_text}</li>')
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                if stripped:
                    html_lines.append(f'<p style="margin:8px 0;line-height:1.6;">{stripped}</p>')
        if in_list:
            html_lines.append('</ul>')
        response_text = (
            '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;'
            'padding:20px;color:#0f172a;line-height:1.6;font-size:15px;">'
            + "".join(html_lines) + "</div>"
        )

    logger.info(f"=== V2 QUERY COMPLETE === {len(response_text)} chars")
    return {
        "response": response_text,
        "sources": result["sources"],
        "context_chunks": result["context_chunks"],
        "format": format,
        "pipeline": "nusf",
    }
