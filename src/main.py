from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import csv
import io
import logging
import os
import time
import uuid
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import threading

_query_executor = ThreadPoolExecutor(max_workers=4)
_upload_progress: Dict[str, Dict[str, Any]] = {}
_predictive_progress: Dict[str, Dict[str, Any]] = {}
_source_file_cache: Dict[str, bytes] = {}
_progress_lock = threading.Lock()

PROGRESS_STAGES = {
    "received": {
        "step": 1,
        "total_steps": 6,
        "en": "We've received your schedule — starting the analysis now...",
        "da": "Vi har modtaget din tidsplan — starter analysen nu..."
    },
    "reading": {
        "step": 2,
        "total_steps": 6,
        "en": "Reading and scanning your document — extracting tables and data...",
        "da": "Læser og scanner dit dokument — henter tabeller og data ud..."
    },
    "extracting": {
        "step": 3,
        "total_steps": 6,
        "en": "Found your schedule data — identifying all activities...",
        "da": "Fandt dine tidsplandata — identificerer alle aktiviteter..."
    },
    "analyzing": {
        "step": 4,
        "total_steps": 6,
        "en": [
            "Nova is reading every row — detecting all delayed activities...",
            "Checking each activity against the reference date and progress...",
            "Classifying tasks — coordination, design, production, bygherre decisions...",
            "Identifying root causes and downstream consequences...",
            "Mapping delay propagation — which tasks block which disciplines...",
            "Building priority ranking — critical now vs monitor...",
            "Generating action recommendations for your project team...",
            "Assessing resource implications — manpower vs coordination bottlenecks...",
            "Writing management conclusion — almost ready...",
        ],
        "da": [
            "Nova læser hver række — finder alle forsinkede aktiviteter...",
            "Tjekker hver aktivitet mod referencedato og fremdrift...",
            "Klassificerer opgaver — koordinering, design, produktion, bygherrebeslutninger...",
            "Identificerer grundårsager og afledte konsekvenser...",
            "Kortlægger forsinkelsespropagering — hvilke opgaver blokerer hvilke discipliner...",
            "Opbygger prioriteringsrangering — kritisk nu vs overvåg...",
            "Genererer handlingsanbefalinger til dit projektteam...",
            "Vurderer ressourceimplikationer — mandskab vs koordineringsflaskehalse...",
            "Skriver ledelseskonklusion — næsten klar...",
        ]
    },
    "formatting": {
        "step": 5,
        "total_steps": 6,
        "en": "Almost there — building your report...",
        "da": "Næsten klar — opbygger din rapport..."
    },
    "complete": {
        "step": 6,
        "total_steps": 6,
        "en": "Your analysis is ready!",
        "da": "Din analyse er klar!"
    },
    # TL-7.8 (brief §42): a BLOCK gating decision (TL-4.6/TL-5.5) is a
    # protective pause, not a failure — it must not share the "error"
    # stage's alarming copy. Kept distinct from "error" so a poller can
    # tell "Nova crashed" from "Nova declined to guess" apart, and render
    # each one differently (see `_truncation_block_response` below).
    "blocked": {
        "step": -1,
        "total_steps": 6,
        "en": "Nova paused this analysis to avoid producing an unreliable result. Review required.",
        "da": "Nova satte denne analyse på pause for at undgå et upålideligt resultat. Gennemgang påkrævet."
    },
    "error": {
        "step": -1,
        "total_steps": 6,
        "en": "Something went wrong during the analysis. Please try again.",
        "da": "Noget gik galt under analysen. Prøv venligst igen."
    }
}

PROGRESS_STAGES_V4 = {
    "received": {
        "step": 1,
        "total_steps": 4,
        "en": "Schedules received — initialising v4 dashboard...",
    },
    "extracting": {
        "step": 2,
        "total_steps": 4,
        "en": "Filtering scope and computing health metrics...",
    },
    "analyzing": {
        "step": 3,
        "total_steps": 4,
        "en": [
            "Identifying changes between schedules...",
            "Computing progress vs expected for all activities...",
            "Assessing point of no return...",
            "Ranking top issues by deviation...",
            "Building action recommendations...",
            "Generating AI insights...",
        ],
    },
    "formatting": {
        "step": 4,
        "total_steps": 4,
        "en": "Building Project Health Dashboard...",
    },
    "complete": {
        "step": 4,
        "total_steps": 4,
        "en": "Your v4 dashboard is ready!",
    },
    "error": {
        "step": -1,
        "total_steps": 4,
        "en": "Analysis failed. Please try again.",
    },
}

def _update_progress(analysis_id: str, stage: str, language: str = "en", detail: str = None):
    if stage not in PROGRESS_STAGES:
        return
    stage_info = PROGRESS_STAGES[stage]
    msg_value = stage_info.get(language, stage_info["en"])
    if isinstance(msg_value, list):
        with _progress_lock:
            prev = _predictive_progress.get(analysis_id)
            prev_idx = prev.get("_msg_idx", -1) if prev and prev.get("stage") == stage else -1
            next_idx = (prev_idx + 1) % len(msg_value)
            msg = msg_value[next_idx]
            _predictive_progress[analysis_id] = {
                "analysis_id": analysis_id,
                "stage": stage,
                "step": stage_info["step"],
                "total_steps": stage_info["total_steps"],
                "message": msg,
                "detail": detail,
                "timestamp": time.time(),
                "_msg_idx": next_idx,
                "_language": language
            }
    else:
        msg = msg_value
        with _progress_lock:
            _predictive_progress[analysis_id] = {
                "analysis_id": analysis_id,
                "stage": stage,
                "step": stage_info["step"],
                "total_steps": stage_info["total_steps"],
                "message": msg,
                "detail": detail,
                "timestamp": time.time(),
                "_language": language
            }

def _update_progress_v4(analysis_id: str, stage: str, detail: str = None):
    if stage not in PROGRESS_STAGES_V4:
        return
    stage_info = PROGRESS_STAGES_V4[stage]
    msg_value = stage_info["en"]
    if isinstance(msg_value, list):
        with _progress_lock:
            prev = _predictive_progress.get(analysis_id)
            prev_idx = prev.get("_msg_idx", -1) if prev and prev.get("stage") == stage else -1
            next_idx = (prev_idx + 1) % len(msg_value)
            msg = msg_value[next_idx]
            _predictive_progress[analysis_id] = {
                "analysis_id": analysis_id,
                "stage": stage,
                "step": stage_info["step"],
                "total_steps": stage_info["total_steps"],
                "message": msg,
                "detail": detail,
                "timestamp": time.time(),
                "_msg_idx": next_idx,
                "_version": "v4",
            }
    else:
        with _progress_lock:
            _predictive_progress[analysis_id] = {
                "analysis_id": analysis_id,
                "stage": stage,
                "step": stage_info["step"],
                "total_steps": stage_info["total_steps"],
                "message": msg_value,
                "detail": detail,
                "timestamp": time.time(),
                "_version": "v4",
            }


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

from src.vector_store import vector_store_manager
from src.agent import rag_agent
from src.predictive_agent import predictive_agent
from src.database import init_pgvector_extension, create_chat_memory_table, save_session_metadata, get_session_metadata, get_session_metadata_history
from src.html_formatter import format_response_as_html
from src.predictive_html_formatter import format_predictive_as_html
from src.pdf_processor import process_pdf_binary, rows_to_compact_csv_chunks
import dataclasses

from src.trust.preflight import TruncationReport, gate_context_completeness
from src.trust.review_queue import build_review_queue


def _parse_history_table_names(value: str | None) -> list[str]:
    if not value:
        return []
    import json as _json

    raw = str(value).strip()
    if not raw:
        return []
    try:
        parsed = _json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def _append_unique(values: list[str], *items: str) -> None:
    seen = set(values)
    for item in items:
        item = str(item or "").strip()
        if item and item not in seen:
            values.append(item)
            seen.add(item)


@asynccontextmanager
async def lifespan(app):
    # Start JVM for MPXJ (must happen after Gunicorn fork, never at import time)
    from src.jvm_init import start_jvm_if_needed
    start_jvm_if_needed()

    # Existing startup logic (DB init + Azure OCR credential check)
    try:
        init_pgvector_extension()
        create_chat_memory_table()
        print("Database initialized successfully")

        from src.azure_ocr import AzureDocumentIntelligence
        is_valid, msg = AzureDocumentIntelligence.check_credentials()
        if is_valid:
            print("Azure Document Intelligence OCR: Ready")
        else:
            raise ValueError(f"Azure OCR required but not configured: {msg}")
    except Exception as e:
        print(f"Startup error: {e}")
        raise

    yield


app = FastAPI(
    title="RAG Agent SaaS",
    description="Azure AI RAG Agent with Supabase pgvector - Upload PDFs and query with AI",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "RAG Agent SaaS API",
        "endpoints": {
            "upload": "POST /upload - Upload 2 PDF schedules for comparison agent",
            "query": "POST /query - Query the comparison AI agent",
            "predictive": "POST /predictive - Upload 2 PDFs for Nova Insight predictive analysis",
            "health": "GET /health - Health check"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


class PdfExportRequest(BaseModel):
    html: str
    filename: Optional[str] = "dashboard.pdf"
    width: Optional[int] = None


@app.post("/export/pdf")
async def export_pdf(req: PdfExportRequest):
    """Render self-contained dashboard HTML to a single wide-page vector PDF.

    Uses headless Chromium (baked into the image at build time), so SVG charts
    stay vector and background colours are preserved. The client sends the exact
    HTML it is displaying and receives the PDF bytes for a silent download.
    """
    from src.pdf_export import html_to_pdf, DEFAULT_PAGE_WIDTH_PX

    if not req.html or not req.html.strip():
        raise HTTPException(status_code=400, detail="html is required")

    width = req.width if (req.width and req.width >= 320) else DEFAULT_PAGE_WIDTH_PX

    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "", (req.filename or "dashboard.pdf")).strip()
    if not safe_name.lower().endswith(".pdf"):
        safe_name = (safe_name or "dashboard") + ".pdf"

    logger.info(f"=== PDF EXPORT REQUEST === filename={safe_name} width={width} html_len={len(req.html)}")

    try:
        pdf_bytes = await html_to_pdf(req.html, page_width_px=width)
    except Exception as e:
        logger.exception("PDF export failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    logger.info(f"=== PDF EXPORT OK === {len(pdf_bytes)} bytes for {safe_name}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@app.post("/upload")
async def upload_schedules(
    session_id: str = Form(...),
    old_session_id: str = Form(...),
    new_session_id: str = Form(...),
    old_schedule: UploadFile = File(...),
    new_schedule: UploadFile = File(...),
    data_format: str = Form("raw"),
):
    logger.info(f"=== UPLOAD REQUEST ===")
    logger.info(f"Session: {session_id}")
    logger.info(f"Old schedule: {old_schedule.filename} -> table: {old_session_id}")
    logger.info(f"New schedule: {new_schedule.filename} -> table: {new_session_id}")
    logger.info(f"Data format: {data_format}")
    
    old_filename = old_schedule.filename or "old_schedule.pdf"
    new_filename = new_schedule.filename or "new_schedule.pdf"
    
    if not _is_allowed_file(old_filename) or not _is_allowed_file(new_filename):
        logger.error("Invalid file type - only PDF, CSV, Excel (.xlsx), MPP, and MS Project XML accepted")
        raise HTTPException(status_code=400, detail="Only PDF, CSV, Excel (.xlsx), Microsoft Project (.mpp), and MS Project XML (.xml) files are accepted")
    
    try:
        old_pdf_bytes = await old_schedule.read()
        new_pdf_bytes = await new_schedule.read()
        logger.info(f"Files read: old={len(old_pdf_bytes)} bytes, new={len(new_pdf_bytes)} bytes")
        _source_file_cache[f"{session_id}:old"] = old_pdf_bytes
        _source_file_cache[f"{session_id}:new"] = new_pdf_bytes
        
        upload_id = str(uuid.uuid4())[:8]
        _upload_progress[upload_id] = {
            "status": "processing",
            "upload_id": upload_id,
            "session_id": session_id,
            "old_filename": old_filename,
            "new_filename": new_filename,
            "started_at": time.time(),
            "old_schedule": {"step": "queued", "detail": "Waiting to start", "progress": 0},
            "new_schedule": {"step": "queued", "detail": "Waiting to start", "progress": 0},
            "overall_progress": 0
        }
        
        loop = asyncio.get_event_loop()
        
        async def _process_upload_background():
            try:
                def progress_cb(file_key, step, detail, progress):
                    _upload_progress[upload_id][file_key]["step"] = step
                    _upload_progress[upload_id][file_key]["detail"] = detail
                    _upload_progress[upload_id][file_key]["progress"] = progress
                    old_p = _upload_progress[upload_id]["old_schedule"]["progress"]
                    new_p = _upload_progress[upload_id]["new_schedule"]["progress"]
                    _upload_progress[upload_id]["overall_progress"] = (old_p + new_p) // 2

                def process_file(file_key, filename, file_bytes, table_id):
                    progress_cb(file_key, "ocr", f"Extracting content from {filename}...", 10)
                    if data_format == "nusf":
                        logger.info(f"  Processing {filename} through NUSF pipeline")
                        progress_cb(file_key, "pipeline", f"Normalizing {filename} to NUSF...", 20)
                        chunks = _process_file_to_nusf_chunks(file_bytes, filename)
                    else:
                        if _is_csv(filename):
                            logger.info(f"  Processing CSV file: {filename}")
                            chunks = _parse_csv_to_chunks(file_bytes, filename)
                        elif _is_mpp(filename):
                            logger.info(f"  Processing MPP file: {filename}")
                            chunks = _process_mpp_to_chunks(file_bytes, filename)
                        elif _is_mspdi(filename):
                            logger.info(f"  Processing MS Project XML file: {filename}")
                            chunks = _process_mspdi_to_chunks(file_bytes, filename)
                        else:
                            logger.info(f"  Processing PDF file: {filename}")
                            chunks = process_pdf_binary(file_bytes, filename)
                    result = vector_store_manager.create_store_from_chunks(
                        session_id, filename, chunks, table_id,
                        progress_callback=lambda step, detail, pct: progress_cb(file_key, step, detail, pct)
                    )
                    progress_cb(file_key, "complete", f"{filename} processed", 100)
                    return result
                
                old_future = loop.run_in_executor(
                    _query_executor,
                    lambda: process_file("old_schedule", old_filename, old_pdf_bytes, old_session_id)
                )
                new_future = loop.run_in_executor(
                    _query_executor,
                    lambda: process_file("new_schedule", new_filename, new_pdf_bytes, new_session_id)
                )
                
                old_result, new_result = await asyncio.gather(old_future, new_future)
                
                save_session_metadata(
                    session_id,
                    old_filename,
                    new_filename,
                    old_session_id,
                    new_session_id,
                    data_format=data_format,
                )
                
                elapsed = time.time() - _upload_progress[upload_id]["started_at"]
                _upload_progress[upload_id].update({
                    "status": "complete",
                    "overall_progress": 100,
                    "elapsed_seconds": round(elapsed, 1),
                    "old_schedule": {
                        "step": "complete",
                        "detail": f"{old_result.get('chunks_processed', 0)} chunks stored",
                        "progress": 100,
                        "table_name": old_result.get("table_name"),
                        "chunks": old_result.get("chunks_processed", 0)
                    },
                    "new_schedule": {
                        "step": "complete",
                        "detail": f"{new_result.get('chunks_processed', 0)} chunks stored",
                        "progress": 100,
                        "table_name": new_result.get("table_name"),
                        "chunks": new_result.get("chunks_processed", 0)
                    }
                })
                logger.info(f"=== UPLOAD COMPLETE ({elapsed:.1f}s) ===")
                
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                _upload_progress[upload_id].update({
                    "status": "error",
                    "error": str(e)
                })
        
        asyncio.create_task(_process_upload_background())
        
        return {
            "status": "processing",
            "upload_id": upload_id,
            "session_id": session_id,
            "message": f"Upload started. Poll GET /upload/progress/{upload_id} for real-time progress."
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/upload/progress/{upload_id}")
async def get_upload_progress(upload_id: str):
    if upload_id not in _upload_progress:
        raise HTTPException(status_code=404, detail="Upload ID not found")
    return _upload_progress[upload_id]


DEV_HOSTS = [
    "a2f76a97-674f-4a1f-9ac6-c5bcb0c92fc9-00-jwtgkqguc1o3.worf.replit.dev",
]

@app.post("/query")
async def query_agent(
    request: Request,
    query: str = Form(...),
    vs_table: str = Form(...),
    old_session_id: str = Form(...),
    new_session_id: str = Form(...),
    language: str = Form("en"),
    format: str = Form(None),
    data_format: str = Form("raw"),
):
    host = request.headers.get("host", "")
    is_dev = any(dev_host in host for dev_host in DEV_HOSTS)
    
    if format is None:
        format = "html"
    
    logger.info(f"=== QUERY REQUEST ===")
    logger.info(f"Host: {host} | Is Dev: {is_dev}")
    logger.info(f"Query: {query[:100]}{'...' if len(query) > 100 else ''}")
    logger.info(f"Session: {vs_table} | Language: {language} | Format: {format}")
    logger.info(f"Vector stores: {old_session_id}, {new_session_id}")
    
    try:
        table_names = [old_session_id, new_session_id]
        
        session_meta = get_session_metadata(vs_table)
        old_filename = session_meta.get("old_filename", "Old Schedule")
        new_filename = session_meta.get("new_filename", "New Schedule")
        old_filename_clean = old_filename.replace(".pdf", "").replace(".PDF", "")
        new_filename_clean = new_filename.replace(".pdf", "").replace(".PDF", "")
        logger.info(f"  File names: {old_filename} / {new_filename}")
        
        is_comparison = rag_agent._is_comparison_query(query)
        
        loop = asyncio.get_event_loop()
        
        result = await loop.run_in_executor(
            _query_executor,
            lambda: rag_agent.query(
                user_query=query,
                table_names=table_names,
                session_id=vs_table,
                language=language,
                top_k=10,
                old_filename=old_filename_clean,
                new_filename=new_filename_clean,
                data_format=data_format,
            )
        )
        
        response_text = result["response"]
        actual_is_comparison = result.get("is_comparison", is_comparison)
        
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
            r"<!--DECISION_ENGINE:", r"<!--HEALTH_DATA:",
        ]
        has_sections = any(_re.search(p, response_text, _re.MULTILINE | _re.IGNORECASE) for p in _STRUCTURED_MARKERS)
        
        if format == "html" and has_sections:
            logger.info(f"Structured response detected — applying full HTML formatter...")
            response_text = format_response_as_html(response_text, language, total_data_rows=result.get("total_data_rows", 0), diff_data=result.get("diff_data"))
        elif format == "html":
            logger.info(f"Conversational response - converting markdown to HTML...")
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
            response_text = f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; padding: 20px; color: #0f172a; line-height: 1.6; font-size: 15px;">{"".join(html_lines)}</div>'
        
        logger.info(f"Response generated: {len(response_text)} chars, {result['context_chunks']} chunks used")
        logger.info(f"=== QUERY COMPLETE ===")
        
        return {
            "response": response_text,
            "sources": result["sources"],
            "context_chunks": result["context_chunks"],
            "format": format
        }
        
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _extract_reference_date(filename: str) -> Optional[str]:
    name = filename.replace(".pdf", "").replace(".PDF", "").strip()

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", name)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            try:
                dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                return dt.strftime("%d-%m-%Y")
            except ValueError:
                pass

    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", name)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", name)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    m = re.search(r"(\d{2})_(\d{2})_(\d{4})", name)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", name)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    m = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", name)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    return None


_GANTT_NOISE_PATTERN = re.compile(
    r'^('
    r'\d{1,2}-\d{2}$|'
    r'\d{2}-\d{2}-\d{2,4}$|'
    r'Kvt\d|'
    r'Side \d|'
    r'\d{4}$|'
    r'[A-ZÆØÅ]{1,5}\([A-ZÆØÅ0-9&;]+\)$|'
    r'[A-ZÆØÅ]{2,4}\s*-\s*[A-ZÆØÅ]{2,4}$|'
    r'[A-ZÆØÅ]{2,6}\s*\(TEGN\s*\d+\)$|'
    r'[A-ZÆØÅ]{1,5}\([A-ZÆØÅ0-9&;]+\)\s*-\s*[A-ZÆØÅ]{1,5}\([A-ZÆØÅ0-9&;]+\)$|'
    r'KL-ING$|'
    r'KL$|'
    r'Ark$|'
    r'ALJ$'
    r')',
    re.IGNORECASE
)


def _clean_gantt_noise(text: str) -> str:
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) < 3:
            continue
        if _GANTT_NOISE_PATTERN.match(stripped):
            continue
        if len(stripped) <= 15 and re.match(r'^[\w\s\-().;/&]+$', stripped) and not any(c.isdigit() and len(stripped) > 8 for c in stripped):
            has_letter = any(c.isalpha() for c in stripped)
            has_colon = ':' in stripped
            has_pipe = '|' in stripped
            has_at = '@' in stripped
            looks_like_task = any(kw in stripped.lower() for kw in ['uge', 'maler', 'tømrer', 'el', 'vvs', 'pap', 'flise', 'gulv', 'loft', 'tag', 'køkken', 'bad', 'fuge', 'montage', 'aflevering'])
            if has_letter and not has_colon and not has_pipe and not has_at and not looks_like_task and stripped.count(' ') <= 2:
                continue
        clean_lines.append(line)
    return "\n".join(clean_lines)


ALLOWED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".mpp", ".xml"}

def _is_allowed_file(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)

def _is_csv(filename: str) -> bool:
    return filename.lower().endswith(".csv")

def _is_mpp(filename: str) -> bool:
    return filename.lower().endswith(".mpp")

def _is_mspdi(filename: str) -> bool:
    return filename.lower().endswith(".xml")


def _process_mpp_to_chunks(file_bytes: bytes, filename: str) -> list[dict]:
    """Extract task rows from an .mpp file and return compact CSV chunks."""
    from ingestion.extractors.mpp import MPPExtractor
    from src.pdf_processor import rows_to_compact_csv_chunks

    extractor = MPPExtractor()
    extracted = extractor.extract_from_bytes(file_bytes, filename)
    headers = extracted.get("headers", [])
    rows = extracted.get("rows", [])
    logger.info(f"  [MPP] {filename}: {len(headers)} columns, {len(rows)} data rows")
    return rows_to_compact_csv_chunks(headers, rows, filename)


def _process_mspdi_to_chunks(file_bytes: bytes, filename: str) -> list[dict]:
    """Extract task rows from an MS Project XML (.xml) file and return compact CSV chunks."""
    from ingestion.extractors.mspdi import MspdiExtractor
    from src.pdf_processor import rows_to_compact_csv_chunks

    extractor = MspdiExtractor()
    extracted = extractor.extract_from_bytes(file_bytes, filename)
    headers = extracted.get("headers", [])
    rows = extracted.get("rows", [])
    logger.info(f"  [MSPDI] {filename}: {len(headers)} columns, {len(rows)} data rows")
    return rows_to_compact_csv_chunks(headers, rows, filename)


def _run_nusf_pipeline(file_bytes: bytes, filename: str):
    """Run the universal ingestion pipeline once and require a valid NUSF
    output — the `ScheduleMetadata` object (with `.activities`), not text
    chunks. Shared by `_process_file_to_nusf_chunks` (legacy text-chunk
    consumers, e.g. RAG query context) and `_run_nusf_predictive_analysis`
    (TL-5.4's deterministic facts path), so a NUSF-format PDF is never OCR'd
    twice for the same request.
    """
    from ingestion.pipeline import IngestionPipeline, PipelineError

    pipeline = IngestionPipeline()
    try:
        schedule_obj, _raw_chunks = pipeline.run_from_bytes(file_bytes, filename)
    except PipelineError as exc:
        raise ValueError(f"NUSF generation failed for '{filename}': {exc}") from exc

    if not schedule_obj.activities:
        raise ValueError(
            f"NUSF generation failed for '{filename}': normalization produced 0 activities"
        )
    return schedule_obj


def _process_file_to_nusf_chunks(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Run the universal ingestion pipeline and require a valid NUSF output.
    This is used when the caller explicitly requests NUSF mode for downstream
    comparison/dashboard flows.
    """
    from ingestion.normalization.engine import to_nusf_chunks

    schedule_obj = _run_nusf_pipeline(file_bytes, filename)

    chunks = to_nusf_chunks(schedule_obj)
    if not chunks:
        raise ValueError(
            f"NUSF generation failed for '{filename}': no NUSF chunks were produced"
        )

    logger.info(
        f"  [NUSF] {filename}: {schedule_obj.metadata.total_activities} activities, "
        f"{len(chunks)} chunk(s), quality={schedule_obj.metadata.parse_quality_score}"
    )
    return chunks


def _run_nusf_predictive_analysis(
    schedule_obj,
    filename_clean: str,
    user_query: str,
    language: str,
    reference_date_str: Optional[str],
) -> dict:
    """TL-5.4: the deterministic-facts + narrative-only predictive path for
    NUSF-format schedules (brief §4, §17). Replaces sending a raw text dump
    to `predictive_agent.analyze()` — the model never sees this schedule's
    raw rows, only the small structured context
    `src/trust/context.py`'s `build_predictive_context` produces, and every
    fact in the final response (`schedule_overview`, `delayed_activities`,
    `downstream_consequences`, the deterministic half of `insight_data`) is
    computed here in Python, never asked of the model
    (`build_response_facts`).

    Only reachable when `data_format == "nusf"` — the raw OCR-text path has
    no structured `Activity` list to compute facts from and is unchanged
    (still `predictive_agent.analyze()`, still carrying its TL-5.2
    correction block as the only safety net for that path; see ADR-021).
    """
    import json as _json
    from datetime import timezone as _timezone, timedelta as _timedelta
    from src.trust.context import build_predictive_context, build_response_facts
    from src.trust.predictive_facts import compute_predictive_facts, detect_delayed_activities

    if reference_date_str:
        ref_date = datetime.strptime(reference_date_str, "%d-%m-%Y").date()
    else:
        ref_date = datetime.now(_timezone(_timedelta(hours=1))).date()  # CET, matches PredictiveAgent's own "today"

    activities = schedule_obj.activities
    delayed = detect_delayed_activities(activities, ref_date)
    facts = compute_predictive_facts(delayed, activities)
    structured_context = build_predictive_context(facts, activities, ref_date)
    response_facts = build_response_facts(facts, activities, filename_clean, ref_date, "NUSF")

    logger.info(
        f"  [NUSF Predictive] {filename_clean}: {len(activities)} activities, "
        f"{len(facts)} delayed (deterministic, no LLM), structured context = "
        f"{len(_json.dumps(structured_context))} bytes"
    )

    return predictive_agent.analyze_from_facts(
        structured_context=structured_context,
        response_facts=response_facts,
        user_query=user_query,
        language=language,
        schedule_filename=filename_clean,
        reference_date=reference_date_str,
    )

def _detect_delimiter(sample: str) -> str:
    counts = {}
    for d in [";", ",", "\t", "|"]:
        counts[d] = sample.count(d)
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","

def _parse_csv_to_chunks(file_bytes: bytes, filename: str) -> list[dict]:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        reader = csv.reader(io.StringIO(text), dialect)
    except csv.Error:
        detected = _detect_delimiter(sample)
        reader = csv.reader(io.StringIO(text), delimiter=detected)

    rows = list(reader)
    if not rows:
        return []

    headers = [h.strip() for h in rows[0]]
    data_rows = rows[1:]

    logger.info(f"  [CSV] {filename}: {len(headers)} columns, {len(data_rows)} data rows")

    return rows_to_compact_csv_chunks(headers, data_rows, filename)


def _build_predictive_context_from_csv(file_bytes: bytes, filename: str) -> tuple[str, TruncationReport]:
    """TL-5.5 wrapper: returns `(context, truncation_report)` — see
    `_build_predictive_context` for the gate."""
    chunks = _parse_csv_to_chunks(file_bytes, filename)
    filename_clean = filename.replace('.csv', '').replace('.CSV', '')
    return _build_predictive_context(chunks, filename_clean)


def _build_predictive_context(chunks: list[dict], filename: str) -> tuple[str, TruncationReport]:
    """Build the raw-text predictive context from extracted chunks.

    TL-5.5 (brief §17, §28): the byte budget is now a backstop, not a
    silent drop. Returns `(context, truncation_report)`; the caller MUST
    act on the report — BLOCK → refuse via
    `_truncation_block_response`, PARTIAL → include the report in the
    response payload so the omission is enumerated, PASS → proceed.

    `gate_context_completeness` (in `src/trust/preflight.py`) owns the
    PASS/PARTIAL/BLOCK decision and the threshold for BLOCK; this
    function only measures (total vs included chunks and bytes) and
    calls it. The pre-TL-5.5 behavior — a `logger.warning` plus silent
    omission — was exactly the failure mode this task exists to close
    (brief §17: "Do not send huge raw OCR dumps to the LLM and ask
    'What is happening?' Instead generate structured verified context";
    the byte cap was always a stopgap, and stopgaps that drop silently
    are worse than the cliff they paper over).
    """
    doc_label = f"Schedule ({filename})"
    MAX_PREDICTIVE_CONTEXT_BYTES = 1_900_000

    table_chunks = [c for c in chunks if c.get("metadata", {}).get("type") == "table"]

    if not table_chunks:
        # "No schedule data could be extracted" — BLOCK (not PASS).
        # There is nothing to analyze, which is a stronger failure than
        # partial coverage, not the absence of one. `gate_context_completeness`
        # already encodes this as BLOCK on `total_chunks == 0`.
        empty = f"[{doc_label}]\nNo schedule data could be extracted.\n"
        return empty, gate_context_completeness(
            total_chunks=0,
            included_chunks=0,
            total_bytes=0,
            included_bytes=0,
        )

    preamble = "\n".join([
        f"[{doc_label}] — COMPLETE SCHEDULE DATA",
        "Scan EVERY row for delayed activities.",
        ""
    ])

    total_bytes = sum(len(c["content"].encode("utf-8")) + 1 for c in table_chunks)
    budget = MAX_PREDICTIVE_CONTEXT_BYTES - len(preamble.encode("utf-8"))
    included_parts = []
    included_bytes = 0
    for chunk in table_chunks:
        chunk_bytes = len(chunk["content"].encode("utf-8")) + 1
        if included_bytes + chunk_bytes > budget:
            # TL-5.5: no `logger.warning` and continue. The truncation
            # report carries the signal; the caller decides
            # PASS/PARTIAL/BLOCK. See module docstring.
            break
        included_parts.append(chunk["content"])
        included_bytes += chunk_bytes

    result = preamble + "\n".join(included_parts) + "\n"
    truncation_report = gate_context_completeness(
        total_chunks=len(table_chunks),
        included_chunks=len(included_parts),
        total_bytes=total_bytes,
        included_bytes=included_bytes,
    )
    total_rows = sum(c.get("metadata", {}).get("row_count", 0) for c in table_chunks)
    logger.info(
        f"  [Predictive] Context: {len(result)} bytes — "
        f"{len(included_parts)}/{len(table_chunks)} chunks, ~{total_rows} rows; "
        f"truncation: {truncation_report.decision}"
    )
    return result, truncation_report


def _truncation_block_response(
    report: TruncationReport,
    analysis_id: str,
    language: str,
    filename: str,
) -> Dict[str, Any]:
    """TL-5.5: structured BLOCK response for `_build_predictive_context`
    gating. Same shape vocabulary as
    `PreflightReport.to_refusal_response` (TL-4.6) so callers don't need
    a second refusal contract.

    TL-7.8 (brief §42): marks progress as 'blocked', not 'error' — a
    BLOCK is Nova protecting the user from an unreliable result, not a
    crash, and collapsing the two into the same polling stage is exactly
    the error-shaped presentation brief §42 asks to replace. Schedules
    cleanup so the analysis id doesn't leak into the progress dict."""
    _update_progress(analysis_id, "blocked", language, "Context truncated beyond BLOCK threshold")
    _schedule_progress_cleanup(analysis_id, delay=60)
    logger.warning(
        f"  [Predictive] BLOCK on context truncation: {report.reason} "
        f"(included {report.included_chunks}/{report.total_chunks} chunks, "
        f"{report.included_bytes}/{report.total_bytes} bytes)"
    )
    response = report.to_refusal_response(language)
    response.update({
        "analysis_id": analysis_id,
        "filename": filename,
    })
    return response


@app.post("/predictive")
async def predictive_analysis(
    schedule: UploadFile = File(...),
    language: str = Form("en"),
    format: str = Form("html"),
    analysis_id: str = Form(None),
    data_format: str = Form("raw"),
):
    start_time = time.time()

    if not analysis_id:
        analysis_id = str(uuid.uuid4())[:12]

    filename = schedule.filename or "schedule.pdf"
    filename_clean = filename.replace(".pdf", "").replace(".PDF", "").replace(".csv", "").replace(".CSV", "").replace(".xml", "").replace(".XML", "").replace(".mpp", "").replace(".MPP", "")

    reference_date = _extract_reference_date(filename)

    _update_progress(analysis_id, "received", language)

    logger.info(f"=== PREDICTIVE REQUEST [{analysis_id}] ===")
    logger.info(f"Schedule: {filename} | Language: {language} | Format: {data_format} | Reference date: {reference_date or 'not found in filename'}")

    if not _is_allowed_file(filename):
        _update_progress(analysis_id, "error", language)
        _schedule_progress_cleanup(analysis_id, delay=60)
        raise HTTPException(status_code=400, detail="Only PDF, CSV, Excel (.xlsx), Microsoft Project (.mpp), and MS Project XML (.xml) files are accepted")

    try:
        file_bytes = await schedule.read()
        logger.info(f"  File read: {len(file_bytes)} bytes")
        _source_file_cache[f"{analysis_id}:single"] = file_bytes

        _update_progress(analysis_id, "reading", language, f"{len(file_bytes) // 1024} KB")

        loop = asyncio.get_event_loop()

        is_csv_file = _is_csv(filename)
        is_mpp_file = _is_mpp(filename)
        is_mspdi_file = _is_mspdi(filename)

        # TL-5.5: `truncation_report` is set by the raw-text branches below.
        # The NUSF branch builds a structured JSON context (no byte-budget
        # gate applies), so it deliberately leaves the report as `None` —
        # the response builder checks for that and omits
        # `context_completeness` rather than publishing a meaningless one.
        truncation_report: Optional[TruncationReport] = None

        if data_format == "nusf":
            logger.info(f"  Running NUSF normalization pipeline...")
            schedule_obj = await loop.run_in_executor(
                _query_executor,
                lambda: _run_nusf_pipeline(file_bytes, filename)
            )
            row_count = len(schedule_obj.activities)
            parse_elapsed = time.time() - start_time
            logger.info(f"  NUSF pipeline complete ({parse_elapsed:.1f}s): {row_count} activities")
            # Not sent to the model (TL-5.4 — see `_run_nusf_predictive_analysis`);
            # kept only so the length-logging line below and the best-effort
            # debug dump further down have a `context` to report on.
            context = f"[NUSF structured facts for {row_count} activities — see structured context, not a text dump]"
        elif is_csv_file:
            logger.info(f"  Parsing CSV directly (no OCR needed)...")
            context, truncation_report = _build_predictive_context_from_csv(file_bytes, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
            row_count = context.count("\n")
            parse_elapsed = time.time() - start_time
            logger.info(f"  CSV parsed in {parse_elapsed:.1f}s")
        elif is_mpp_file:
            logger.info(f"  Parsing MPP via MPXJ (no OCR needed)...")
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: _process_mpp_to_chunks(file_bytes, filename)
            )
            table_count = len(chunks)
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            parse_elapsed = time.time() - start_time
            logger.info(f"  MPP parsed in {parse_elapsed:.1f}s: {table_count} chunks, ~{row_count} rows")
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
        elif is_mspdi_file:
            logger.info(f"  Parsing MS Project XML (no OCR needed)...")
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: _process_mspdi_to_chunks(file_bytes, filename)
            )
            table_count = len(chunks)
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            parse_elapsed = time.time() - start_time
            logger.info(f"  MSPDI parsed in {parse_elapsed:.1f}s: {table_count} chunks, ~{row_count} rows")
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
        else:
            logger.info(f"  Running OCR on PDF...")
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: process_pdf_binary(file_bytes, filename)
            )

            table_count = len(chunks)
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            ocr_elapsed = time.time() - start_time
            logger.info(f"  OCR complete ({ocr_elapsed:.1f}s): {table_count} compact CSV chunks, ~{row_count} rows")

            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)

        _update_progress(analysis_id, "extracting", language, f"{row_count} activities")
        logger.info(f"  Context built: {len(context)} chars")

        _update_progress(analysis_id, "analyzing", language, f"{row_count} activities")

        logger.info(f"  Running Nova Insight predictive analysis...")
        predictive_user_query = "Execute full two-phase analysis: detect ALL delayed activities (Phase 1) and produce decision support with root cause analysis, priority ranking, action recommendations, and resource assessment (Phase 2)"
        if data_format == "nusf":
            # TL-5.4 (brief §4, §17): deterministic facts + narrative-only
            # model call. `schedule_obj` came from the nusf branch above.
            predictive_result = await loop.run_in_executor(
                _query_executor,
                lambda: _run_nusf_predictive_analysis(
                    schedule_obj, filename_clean, predictive_user_query, language, reference_date,
                )
            )
        else:
            predictive_result = await loop.run_in_executor(
                _query_executor,
                lambda: predictive_agent.analyze(
                    context=context,
                    user_query=predictive_user_query,
                    language=language,
                    schedule_filename=filename_clean,
                    reference_date=reference_date,
                    data_format=data_format,
                )
            )

        predictive_json = predictive_result.get("predictive_json", None)
        predictive_text = predictive_result.get("predictive_insights", "")
        predictive_status = predictive_result.get("status", "error")
        predictive_model = predictive_result.get("model", "")

        _update_progress(analysis_id, "formatting", language)

        if format == "html" and predictive_json:
            predictive_text = format_predictive_as_html(predictive_json, language)
        elif format == "html" and predictive_text:
            predictive_text = format_predictive_as_html(predictive_text, language)

        elapsed = time.time() - start_time
        logger.info(f"  Predictive response: {len(predictive_text)} chars, status: {predictive_status}, json={'yes' if predictive_json else 'no'}")
        logger.info(f"=== PREDICTIVE COMPLETE [{analysis_id}] ({elapsed:.1f}s) ===")

        import datetime as _dt
        _debug_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis_debug.txt")
        try:
            with open(_debug_path, "w", encoding="utf-8") as _f:
                _f.write(f"{'='*90}\n")
                _f.write(f"  NOVA INSIGHT — COMPLETE ANALYSIS ANATOMY\n")
                _f.write(f"  Updated: {_dt.datetime.now().isoformat()}\n")
                _f.write(f"{'='*90}\n\n")

                _f.write(f"{'─'*90}\n")
                _f.write(f"  STEP 1: REQUEST RECEIVED\n")
                _f.write(f"{'─'*90}\n")
                _f.write(f"  File:           {filename}\n")
                _f.write(f"  Size:           {len(file_bytes)} bytes ({len(file_bytes)//1024} KB)\n")
                _f.write(f"  Reference Date: {reference_date}\n")
                _f.write(f"  Language:       {language}\n")
                _f.write(f"  Format:         {format}\n")
                _f.write(f"  Analysis ID:    {analysis_id}\n\n")

                _f.write(f"{'─'*90}\n")
                _f.write(f"  STEP 2: DATA EXTRACTION\n")
                _f.write(f"{'─'*90}\n")
                if is_csv_file:
                    _f.write(f"  CSV rows:       ~{row_count}\n\n")
                elif is_mpp_file:
                    _f.write(f"  MPP parse time: {parse_elapsed:.1f}s\n")
                    _f.write(f"  Table chunks:   {table_count}\n")
                    _f.write(f"  Total rows:     ~{row_count}\n")
                    _f.write(f"  Total chunks:   {len(chunks)}\n\n")
                    _f.write(f"  --- COMPLETE MPP EXTRACTION OUTPUT (all chunks) ---\n\n")
                    for ci, c in enumerate(chunks):
                        ctype = c.get("metadata", {}).get("type", "unknown")
                        ccontent = c.get("content", "")
                        _f.write(f"  [CHUNK {ci} | type={ctype} | {len(ccontent)} chars]\n")
                        _f.write(ccontent)
                        _f.write(f"\n\n")
                elif is_mspdi_file:
                    _f.write(f"  MSPDI parse time: {parse_elapsed:.1f}s\n")
                    _f.write(f"  Table chunks:     {table_count}\n")
                    _f.write(f"  Total rows:       ~{row_count}\n")
                    _f.write(f"  Total chunks:     {len(chunks)}\n\n")
                    _f.write(f"  --- COMPLETE MSPDI EXTRACTION OUTPUT (all chunks) ---\n\n")
                    for ci, c in enumerate(chunks):
                        ctype = c.get("metadata", {}).get("type", "unknown")
                        ccontent = c.get("content", "")
                        _f.write(f"  [CHUNK {ci} | type={ctype} | {len(ccontent)} chars]\n")
                        _f.write(ccontent)
                        _f.write(f"\n\n")
                else:
                    _f.write(f"  OCR Time:       {ocr_elapsed:.1f}s\n")
                    _f.write(f"  Table chunks:   {table_count}\n")
                    _f.write(f"  Total rows:     ~{row_count}\n")
                    _f.write(f"  Total chunks:   {len(chunks)}\n\n")
                    _f.write(f"  --- COMPLETE OCR OUTPUT (all chunks) ---\n\n")
                    for ci, c in enumerate(chunks):
                        ctype = c.get("metadata", {}).get("type", "unknown")
                        ccontent = c.get("content", "")
                        _f.write(f"  [CHUNK {ci} | type={ctype} | {len(ccontent)} chars]\n")
                        _f.write(ccontent)
                        _f.write(f"\n\n")

                _f.write(f"{'─'*90}\n")
                _f.write(f"  STEP 3: CONTEXT PASSED TO LLM ({len(context)} chars)\n")
                _f.write(f"{'─'*90}\n\n")
                _f.write(context)
                _f.write(f"\n\n")

                sys_prompt = predictive_result.get("system_prompt", "")
                usr_msg = predictive_result.get("user_message", "")
                if sys_prompt:
                    _f.write(f"{'─'*90}\n")
                    _f.write(f"  STEP 4A: SYSTEM PROMPT SENT TO LLM ({len(sys_prompt)} chars)\n")
                    _f.write(f"{'─'*90}\n\n")
                    _f.write(sys_prompt)
                    _f.write(f"\n\n")

                if usr_msg:
                    _f.write(f"{'─'*90}\n")
                    _f.write(f"  STEP 4B: USER MESSAGE SENT TO LLM ({len(usr_msg)} chars)\n")
                    _f.write(f"{'─'*90}\n\n")
                    _f.write(usr_msg)
                    _f.write(f"\n\n")

                _f.write(f"{'─'*90}\n")
                _f.write(f"  STEP 5: RAW LLM RESPONSE\n")
                _f.write(f"{'─'*90}\n")
                _f.write(f"  Model:    {predictive_model}\n")
                _f.write(f"  Status:   {predictive_status}\n")
                _f.write(f"  Tokens:   {predictive_result.get('usage_info', 'N/A')}\n")
                _f.write(f"  Time:     {elapsed:.1f}s total\n\n")

                reasoning = predictive_result.get("reasoning_content")
                if reasoning:
                    _f.write(f"  --- LLM REASONING ---\n\n")
                    _f.write(reasoning)
                    _f.write(f"\n\n")

                raw_llm = predictive_result.get("raw_llm_response", "")
                if raw_llm:
                    _f.write(f"  --- RAW JSON RESPONSE ({len(raw_llm)} chars) ---\n\n")
                    try:
                        pretty = json.dumps(json.loads(raw_llm), indent=2, ensure_ascii=False)
                        _f.write(pretty)
                    except Exception:
                        _f.write(raw_llm)
                    _f.write(f"\n\n")

                if predictive_json:
                    delayed = predictive_json.get("delayed_activities", [])
                    _f.write(f"{'─'*90}\n")
                    _f.write(f"  STEP 6: RESULT SUMMARY\n")
                    _f.write(f"{'─'*90}\n")
                    overview = predictive_json.get("schedule_overview", {})
                    _f.write(f"  Total Activities: {overview.get('total_activities', '?')}\n")
                    _f.write(f"  Delayed:          {overview.get('delayed_count', '?')}\n")
                    _f.write(f"  Areas:            {', '.join(overview.get('areas_covered', []))}\n")
                    _f.write(f"  Format:           {overview.get('format_detected', '?')}\n\n")
                    if delayed:
                        _f.write(f"  Delayed Activity IDs: {[a.get('id','?') for a in delayed]}\n\n")
                        _f.write(f"  {'ID':<8} {'TASK NAME':<50} {'START':<14} {'DAYS':<6} {'PRIORITY'}\n")
                        _f.write(f"  {'─'*8} {'─'*50} {'─'*14} {'─'*6} {'─'*15}\n")
                        for a in delayed:
                            _f.write(f"  {a.get('id','?'):<8} {a.get('task_name','?')[:50]:<50} {a.get('start_date','?'):<14} {a.get('days_overdue','?'):<6} {a.get('priority','?')}\n")
                    _f.write(f"\n")

                _f.write(f"{'='*90}\n")
                _f.write(f"  END OF ANALYSIS ANATOMY\n")
                _f.write(f"{'='*90}\n")

            logger.info(f"  Debug file saved: analysis_debug.txt")
        except Exception as _e:
            logger.warning(f"  Failed to save debug file: {_e}")

        _update_progress(analysis_id, "complete", language)

        _schedule_progress_cleanup(analysis_id)

        # TL-5.5 (brief §17, §28): when context completeness is PARTIAL,
        # enumerate the omission in the response so the caller can act on
        # it. PASS is omitted (nothing to report) and BLOCK never reaches
        # this point (returned earlier via `_truncation_block_response`).
        response_payload: Dict[str, Any] = {
            "analysis_id": analysis_id,
            "predictive_insights": predictive_text,
            "predictive_status": predictive_status,
            "predictive_model": predictive_model,
            "filename": filename,
            "reference_date": reference_date,
            "format": format,
            "processing_time_seconds": round(elapsed, 1)
        }
        if truncation_report is not None and truncation_report.decision == "PARTIAL":
            response_payload["context_completeness"] = truncation_report.to_dict()
        return response_payload

    except Exception as e:
        logger.error(f"Predictive analysis failed: {e}")
        _update_progress(analysis_id, "error", language, str(e))
        _schedule_progress_cleanup(analysis_id, delay=120)
        raise HTTPException(status_code=500, detail=str(e))


def _schedule_progress_cleanup(analysis_id: str, delay: int = 300):
    def cleanup():
        time.sleep(delay)
        with _progress_lock:
            _predictive_progress.pop(analysis_id, None)
    threading.Thread(target=cleanup, daemon=True).start()


@app.get("/predictive/progress/{analysis_id}")
async def get_predictive_progress(analysis_id: str):
    with _progress_lock:
        progress = _predictive_progress.get(analysis_id)

    if not progress:
        raise HTTPException(
            status_code=404,
            detail="No analysis found with this ID. It may have completed or expired."
        )

    if progress.get("stage") == "analyzing":
        version = progress.get("_version", "v1")
        if version == "v4":
            _update_progress_v4(analysis_id, "analyzing", progress.get("detail"))
        else:
            lang = progress.get("_language", "en")
            _update_progress(analysis_id, "analyzing", lang, progress.get("detail"))
        with _progress_lock:
            progress = _predictive_progress.get(analysis_id, progress)

    resp = {k: v for k, v in progress.items() if not k.startswith("_")}
    return resp


@app.post("/v5-graph/compare")
async def compare_v5_graph(
    session_id: str = Form(...),
    old_session_id: str = Form(...),
    new_session_id: str = Form(...),
    scope_filter: str = Form(None),
    reference_date: str = Form(None),
    language: str = Form("en"),
    format: str = Form("html"),
    analysis_id: str = Form(None),
    data_format: str = Form(None),
):
    import json as _json
    if not analysis_id:
        analysis_id = str(uuid.uuid4())[:12]

    start_time = time.time()
    logger.info(f"=== COMPARE V5 GRAPH REQUEST [{analysis_id}] ===")
    logger.info(f"Session: {session_id} | Old DB: {old_session_id} | New DB: {new_session_id}")
    logger.info(f"Scope Filter: {scope_filter} | Reference Date: {reference_date}")

    _update_progress_v4(analysis_id, "received")

    try:
        from src.experimental.compare_v5_graph_agent import compare_v5_graph_agent
        from src.experimental.html_formatter_v5_graph import format_compare_v5_graph_as_html

        session_meta = get_session_metadata(session_id)
        old_filename = session_meta.get("old_filename", "Old Schedule").replace(".pdf", "")
        new_filename = session_meta.get("new_filename", "New Schedule").replace(".pdf", "")
        effective_data_format = data_format or session_meta.get("data_format") or "raw"
        require_nusf = effective_data_format == "nusf"
        logger.info(f"V5 graph compare data format: {effective_data_format}")

        _update_progress_v4(analysis_id, "extracting")

        loop = asyncio.get_event_loop()
        tables = [old_session_id, new_session_id]

        _update_progress_v4(analysis_id, "analyzing")

        result = await loop.run_in_executor(
            _query_executor,
            lambda: compare_v5_graph_agent.analyze(
                scope_filter=scope_filter or "All activities",
                reference_date=reference_date or "Unknown",
                table_names=tables,
                session_id=session_id,
                old_filename=old_filename,
                new_filename=new_filename,
                require_nusf=require_nusf,
                language=language,
            ),
        )

        json_data = result.get("json", {})

        _update_progress_v4(analysis_id, "formatting")

        if format == "html":
            response_text = format_compare_v5_graph_as_html(json_data, language)
        else:
            response_text = _json.dumps(json_data, ensure_ascii=False)

        _update_progress_v4(analysis_id, "complete")
        _schedule_progress_cleanup(analysis_id)

        elapsed = time.time() - start_time
        logger.info(f"=== COMPARE V5 GRAPH COMPLETE [{analysis_id}] ({elapsed:.1f}s) ===")

        return {
            "analysis_id": analysis_id,
            "response": response_text,
            "json_data": json_data,
            "context_chunks": result.get("context_chunks", 0),
            "format": format,
        }

    except Exception as e:
        logger.error(f"Compare V5 Graph failed: {e}")
        _update_progress_v4(analysis_id, "error", str(e))
        _schedule_progress_cleanup(analysis_id, delay=120)
        raise HTTPException(status_code=500, detail=str(e))


def _populate_health_audit_trail(
    analysis_id: str,
    session_id: str,
    old_filename: str,
    new_filename: str,
    require_nusf: bool,
    effective_data_format: str,
    review_queue: list,
    json_data: dict,
    format: str,
    language: str,
    tables: list,
    context_chunks: int,
):
    """Populate Brief §40 audit chain for a comparison health analysis."""
    from src.trust.audit import AuditStage, audit_store
    from src.trust.versioning import AnalysisVersions

    trail = audit_store.get_or_create(analysis_id, project_id=analysis_id)

    parser_ver = "nusf-pipeline-v2.1" if require_nusf else "v1-parser-v1.0"
    applied_corrections = len(json_data.get("applied_mappings", []))
    corrections_ver = f"corrections-v{applied_corrections}" if applied_corrections > 0 else "corrections:none"
    model_ver = "deterministic-comparison-engine"
    schedule_rev = f"old:{old_filename}|new:{new_filename}"

    versions = AnalysisVersions(
        parser=parser_ver,
        matching_algorithm="nusf-matcher-v3.2",
        analysis_engine="nusf-compare-engine-v1.4",
        prompt="comparison-prompt-v1.0",
        model=model_ver,
        schedule_revision=schedule_rev,
        manual_corrections=corrections_ver,
    )
    trail.set_versions(versions)

    if not trail.has_stage(AuditStage.SCHEDULE_UPLOADED):
        trail.add_entry(
            AuditStage.SCHEDULE_UPLOADED,
            {
                "old_filename": old_filename,
                "new_filename": new_filename,
                "session_id": session_id,
                "schedule_revision": schedule_rev,
            },
        )
    if not trail.has_stage(AuditStage.PARSER_VERSION):
        trail.add_entry(
            AuditStage.PARSER_VERSION,
            {
                "parser": "nusf_pipeline" if require_nusf else "v1_parser",
                "version": parser_ver,
                "parser_version": parser_ver,
                "format": effective_data_format,
            },
        )
    if not trail.has_stage(AuditStage.OCR_PROVIDER):
        trail.add_entry(
            AuditStage.OCR_PROVIDER,
            {
                "provider": "azure_document_intelligence",
                "api_version": "2024-02-29-preview",
            },
        )
    if not trail.has_stage(AuditStage.CONFIDENCE_RESULTS):
        trail.add_entry(
            AuditStage.CONFIDENCE_RESULTS,
            {
                "review_queue_count": len(review_queue),
                "unverified_activities_count": len(
                    json_data.get("requires_verification_activities", [])
                ),
            },
        )
    if not trail.has_stage(AuditStage.MATCHES_GENERATED):
        trail.add_entry(
            AuditStage.MATCHES_GENERATED,
            {
                "algorithm_version": "nusf-matcher-v3.2",
                "matching_algorithm": "nusf-matcher-v3.2",
                "matched_count": len(
                    json_data.get("matching_pairs", [])
                    or json_data.get("changed_activities", [])
                ),
                "unmatched_count": len(
                    json_data.get("requires_verification_activities", [])
                ),
            },
        )
    if not trail.has_stage(AuditStage.MANUAL_CORRECTIONS):
        trail.add_entry(
            AuditStage.MANUAL_CORRECTIONS,
            {
                "corrections_version": corrections_ver,
                "applied_corrections_count": applied_corrections,
            },
        )
    if not trail.has_stage(AuditStage.ANALYSIS_VERSION):
        trail.add_entry(
            AuditStage.ANALYSIS_VERSION,
            {
                "engine": "nusf-compare-engine-v1.4",
                "engine_version": "nusf-compare-engine-v1.4",
                "version": "nusf-compare-engine-v1.4",
                "rules": "strict_error_gating",
            },
        )
    if not trail.has_stage(AuditStage.AGENT_ANSWER):
        trail.add_entry(
            AuditStage.AGENT_ANSWER,
            {
                "status": json_data.get("project_health", {}).get(
                    "status", "completed"
                ),
                "model": model_ver,
                "model_version": model_ver,
                "prompt": "comparison-prompt-v1.0",
                "prompt_version": "comparison-prompt-v1.0",
                "format": format,
                "language": language,
            },
        )
    if not trail.has_stage(AuditStage.EVIDENCE_USED):
        trail.add_entry(
            AuditStage.EVIDENCE_USED,
            {
                "tables": tables,
                "context_chunks": context_chunks,
            },
        )

    # TL-9.4 / Brief §38: continuous trust metrics computation and persistence
    from src.trust.metrics import compute_live_metrics, metrics_store
    metrics_snap = compute_live_metrics(
        analysis_id=analysis_id,
        comparison_data=json_data,
        review_queue=review_queue,
        project_id=analysis_id,
    )
    metrics_store.record(metrics_snap)

    return trail


@app.post("/version-1.0/health")
async def version_1_health_dashboard(
    session_id: str = Form(...),
    old_session_id: str = Form(...),
    new_session_id: str = Form(...),
    scope_filter: str = Form(None),
    reference_date: str = Form(None),
    language: str = Form("en"),
    format: str = Form("html"),
    analysis_id: str = Form(None),
    data_format: str = Form(None),
    history_table_names: str = Form(None),
):
    """Nova Insight Version 1.0 project health dashboard.

    Production baseline: v5-graph comparison facts + the simpler V1 decision
    dashboard formatter.
    """
    import json as _json

    if not analysis_id:
        analysis_id = str(uuid.uuid4())[:12]

    start_time = time.time()
    logger.info(f"=== VERSION 1.0 HEALTH REQUEST [{analysis_id}] ===")
    logger.info(f"Session: {session_id} | Old DB: {old_session_id} | New DB: {new_session_id}")
    logger.info(f"Scope Filter: {scope_filter} | Reference Date: {reference_date}")

    _update_progress_v4(analysis_id, "received")

    try:
        from src.experimental.compare_v5_graph_agent import compare_v5_graph_agent
        from src.version_1_0 import format_health_v1_as_html

        session_meta = get_session_metadata(session_id)
        old_filename = session_meta.get("old_filename", "Old Schedule").replace(".pdf", "")
        new_filename = session_meta.get("new_filename", "New Schedule").replace(".pdf", "")
        effective_data_format = data_format or session_meta.get("data_format") or "raw"
        require_nusf = effective_data_format == "nusf"

        _update_progress_v4(analysis_id, "extracting")

        loop = asyncio.get_event_loop()
        tables = [old_session_id, new_session_id]
        history_labels = {
            old_session_id: old_filename,
            new_session_id: new_filename,
        }
        try:
            for meta in get_session_metadata_history(session_id):
                old_table = meta.get("old_table_name")
                new_table = meta.get("new_table_name")
                old_label = (meta.get("old_filename") or old_table or "").replace(".pdf", "")
                new_label = (meta.get("new_filename") or new_table or "").replace(".pdf", "")
                _append_unique(tables, old_table, new_table)
                if old_table and old_label:
                    history_labels[old_table] = old_label
                if new_table and new_label:
                    history_labels[new_table] = new_label
        except Exception as history_ex:
            logger.warning(f"Could not load session history for V1 graph: {history_ex}")
        _append_unique(tables, *_parse_history_table_names(history_table_names))

        _update_progress_v4(analysis_id, "analyzing")

        result = await loop.run_in_executor(
            _query_executor,
            lambda: compare_v5_graph_agent.analyze(
                scope_filter=scope_filter or "All activities",
                reference_date=reference_date or "Unknown",
                table_names=tables,
                session_id=session_id,
                old_filename=old_filename,
                new_filename=new_filename,
                require_nusf=require_nusf,
                language=language,
                history_labels=history_labels,
            ),
        )

        json_data = result.get("json", {})

        _update_progress_v4(analysis_id, "formatting")

        if format == "html":
            response_text = format_health_v1_as_html(json_data, language)
        else:
            response_text = _json.dumps(json_data, ensure_ascii=False)

        _update_progress_v4(analysis_id, "complete")
        _schedule_progress_cleanup(analysis_id)

        elapsed = time.time() - start_time
        logger.info(f"=== VERSION 1.0 HEALTH COMPLETE [{analysis_id}] ({elapsed:.1f}s) ===")

        # TL-8.1 (brief §25): every review-item category derivable from
        # what this endpoint already computed, at zero extra cost to the
        # caller — `json_data` (already returned below) is the same dict
        # `build_review_queue` reads from. `analysis_id` is the scoping
        # key; the Flask backend persisting this response may re-key it
        # under its own comparison id / company id, per
        # `ReviewQueueStore`'s own "opaque key, caller decides" contract.
        review_queue = [
            dataclasses.asdict(item)
            for item in build_review_queue(
                analysis_id,
                requires_verification_activities=json_data.get("requires_verification_activities", []),
            )
        ]

        trail = _populate_health_audit_trail(
            analysis_id=analysis_id,
            session_id=session_id,
            old_filename=old_filename,
            new_filename=new_filename,
            require_nusf=require_nusf,
            effective_data_format=effective_data_format,
            review_queue=review_queue,
            json_data=json_data,
            format=format,
            language=language,
            tables=tables,
            context_chunks=result.get("context_chunks", 0),
        )

        from src.trust.metrics import metrics_store
        latest_metrics = metrics_store.get_latest(project_id=analysis_id)

        return {
            "analysis_id": analysis_id,
            "response": response_text,
            "json_data": json_data,
            "review_queue": review_queue,
            "versions": trail.get_versions(),
            "trust_metrics": latest_metrics.to_summary_dict() if latest_metrics else None,
            "audit_trail": trail.reconstruct_answer(),
            "context_chunks": result.get("context_chunks", 0),
            "format": format,
            "version": "1.0",
            "processing_time_seconds": round(elapsed, 1),
        }

    except Exception as e:
        logger.error(f"Version 1.0 health dashboard failed: {e}", exc_info=True)
        _update_progress_v4(analysis_id, "error", str(e))
        _schedule_progress_cleanup(analysis_id, delay=120)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/version-1.0/kemp/health")
async def version_1_kemp_health_dashboard(
    session_id: str = Form(...),
    old_session_id: str = Form(...),
    new_session_id: str = Form(...),
    scope_filter: str = Form(None),
    reference_date: str = Form(None),
    language: str = Form("da"),
    format: str = Form("html"),
    analysis_id: str = Form(None),
    data_format: str = Form(None),
    history_table_names: str = Form(None),
):
    """Nova Insight Version 1.0 health dashboard — Kemp variant.

    Same v5-graph comparison facts as ``/version-1.0/health``, but the
    rendered HTML omits the activities-analyzed / critical-activities /
    point-of-no-return KPI pills, the critical-path (point-of-no-return)
    table, and any rows in the remaining tables that also appear in the
    critical-path set.
    """
    import json as _json

    if not analysis_id:
        analysis_id = str(uuid.uuid4())[:12]

    start_time = time.time()
    logger.info(f"=== VERSION 1.0 KEMP HEALTH REQUEST [{analysis_id}] ===")
    logger.info(f"Session: {session_id} | Old DB: {old_session_id} | New DB: {new_session_id}")
    logger.info(f"Scope Filter: {scope_filter} | Reference Date: {reference_date}")

    _update_progress_v4(analysis_id, "received")

    try:
        from src.experimental.compare_v5_graph_agent import compare_v5_graph_agent
        from src.version_1_0 import format_kemp_v1_as_html

        session_meta = get_session_metadata(session_id)
        old_filename = session_meta.get("old_filename", "Old Schedule").replace(".pdf", "")
        new_filename = session_meta.get("new_filename", "New Schedule").replace(".pdf", "")
        effective_data_format = data_format or session_meta.get("data_format") or "raw"
        require_nusf = effective_data_format == "nusf"

        _update_progress_v4(analysis_id, "extracting")

        loop = asyncio.get_event_loop()
        tables = [old_session_id, new_session_id]
        history_labels = {
            old_session_id: old_filename,
            new_session_id: new_filename,
        }
        try:
            for meta in get_session_metadata_history(session_id):
                old_table = meta.get("old_table_name")
                new_table = meta.get("new_table_name")
                old_label = (meta.get("old_filename") or old_table or "").replace(".pdf", "")
                new_label = (meta.get("new_filename") or new_table or "").replace(".pdf", "")
                _append_unique(tables, old_table, new_table)
                if old_table and old_label:
                    history_labels[old_table] = old_label
                if new_table and new_label:
                    history_labels[new_table] = new_label
        except Exception as history_ex:
            logger.warning(f"Could not load session history for V1 Kemp: {history_ex}")
        _append_unique(tables, *_parse_history_table_names(history_table_names))

        _update_progress_v4(analysis_id, "analyzing")

        result = await loop.run_in_executor(
            _query_executor,
            lambda: compare_v5_graph_agent.analyze(
                scope_filter=scope_filter or "All activities",
                reference_date=reference_date or "Unknown",
                table_names=tables,
                session_id=session_id,
                old_filename=old_filename,
                new_filename=new_filename,
                require_nusf=require_nusf,
                language=language,
                history_labels=history_labels,
            ),
        )

        json_data = result.get("json", {})

        _update_progress_v4(analysis_id, "formatting")

        if format == "html":
            response_text = format_kemp_v1_as_html(json_data, language)
        else:
            response_text = _json.dumps(json_data, ensure_ascii=False)

        _update_progress_v4(analysis_id, "complete")
        _schedule_progress_cleanup(analysis_id)

        elapsed = time.time() - start_time
        logger.info(f"=== VERSION 1.0 KEMP HEALTH COMPLETE [{analysis_id}] ({elapsed:.1f}s) ===")

        # TL-8.1 (brief §25): see the sibling `/version-1.0/health` route
        # for the full rationale — same zero-extra-cost derivation.
        review_queue = [
            dataclasses.asdict(item)
            for item in build_review_queue(
                analysis_id,
                requires_verification_activities=json_data.get("requires_verification_activities", []),
            )
        ]

        trail = _populate_health_audit_trail(
            analysis_id=analysis_id,
            session_id=session_id,
            old_filename=old_filename,
            new_filename=new_filename,
            require_nusf=require_nusf,
            effective_data_format=effective_data_format,
            review_queue=review_queue,
            json_data=json_data,
            format=format,
            language=language,
            tables=tables,
            context_chunks=result.get("context_chunks", 0),
        )

        from src.trust.metrics import metrics_store
        latest_metrics = metrics_store.get_latest(project_id=analysis_id)

        return {
            "analysis_id": analysis_id,
            "response": response_text,
            "json_data": json_data,
            "review_queue": review_queue,
            "versions": trail.get_versions(),
            "trust_metrics": latest_metrics.to_summary_dict() if latest_metrics else None,
            "audit_trail": trail.reconstruct_answer(),
            "context_chunks": result.get("context_chunks", 0),
            "format": format,
            "version": "1.0-kemp",
            "processing_time_seconds": round(elapsed, 1),
        }

    except Exception as e:
        logger.error(f"Version 1.0 Kemp health dashboard failed: {e}", exc_info=True)
        _update_progress_v4(analysis_id, "error", str(e))
        _schedule_progress_cleanup(analysis_id, delay=120)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/version-1.0/predictive")
async def version_1_predictive_dashboard(
    schedule: UploadFile = File(...),
    language: str = Form("en"),
    format: str = Form("html"),
    analysis_id: str = Form(None),
    data_format: str = Form("raw"),
):
    """Nova Insight Version 1.0 predictive decision dashboard."""
    import json as _json

    start_time = time.time()
    if not analysis_id:
        analysis_id = str(uuid.uuid4())[:12]

    filename = schedule.filename or "schedule.pdf"
    filename_clean = (
        filename.replace(".pdf", "").replace(".PDF", "")
        .replace(".csv", "").replace(".CSV", "")
        .replace(".xml", "").replace(".XML", "")
        .replace(".mpp", "").replace(".MPP", "")
    )
    reference_date = _extract_reference_date(filename)

    _update_progress(analysis_id, "received", language)
    logger.info(f"=== VERSION 1.0 PREDICTIVE REQUEST [{analysis_id}] ===")
    logger.info(f"Schedule: {filename} | Language: {language} | Format: {data_format} | Reference date: {reference_date or 'not found'}")

    if not _is_allowed_file(filename):
        _update_progress(analysis_id, "error", language)
        _schedule_progress_cleanup(analysis_id, delay=60)
        raise HTTPException(status_code=400, detail="Only PDF, CSV, Excel (.xlsx), Microsoft Project (.mpp), and MS Project XML (.xml) files are accepted")

    try:
        from src.version_1_0 import format_predictive_v1_as_html

        file_bytes = await schedule.read()
        _update_progress(analysis_id, "reading", language, f"{len(file_bytes) // 1024} KB")

        loop = asyncio.get_event_loop()
        is_csv_file = _is_csv(filename)
        is_mpp_file = _is_mpp(filename)
        is_mspdi_file = _is_mspdi(filename)

        # TL-5.5: `truncation_report` is set by the raw-text branches below.
        # The NUSF branch builds a structured JSON context (no byte-budget
        # gate applies), so it deliberately leaves the report as `None` —
        # the response builder checks for that and omits
        # `context_completeness` rather than publishing a meaningless one.
        truncation_report: Optional[TruncationReport] = None

        if data_format == "nusf":
            schedule_obj = await loop.run_in_executor(
                _query_executor,
                lambda: _run_nusf_pipeline(file_bytes, filename),
            )
            row_count = len(schedule_obj.activities)
            context = f"[NUSF structured facts for {row_count} activities — see structured context, not a text dump]"
        elif is_csv_file:
            context, truncation_report = _build_predictive_context_from_csv(file_bytes, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
            row_count = context.count("\n")
        elif is_mpp_file:
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: _process_mpp_to_chunks(file_bytes, filename),
            )
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
        elif is_mspdi_file:
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: _process_mspdi_to_chunks(file_bytes, filename),
            )
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
        else:
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: process_pdf_binary(file_bytes, filename),
            )
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)

        _update_progress(analysis_id, "extracting", language, f"{row_count} activities")
        _update_progress(analysis_id, "analyzing", language, f"{row_count} activities")

        v1_predictive_user_query = (
            "Execute Nova Insight Version 1.0 predictive analysis: produce concise decision support, "
            "preserve real activity IDs, include location/phase/trade evidence when visible, avoid invented "
            "forecast values, and rank the top actions a project manager should take now."
        )
        if data_format == "nusf":
            # TL-5.4 (brief §4, §17): deterministic facts + narrative-only model call.
            predictive_result = await loop.run_in_executor(
                _query_executor,
                lambda: _run_nusf_predictive_analysis(
                    schedule_obj, filename_clean, v1_predictive_user_query, language, reference_date,
                ),
            )
        else:
            predictive_result = await loop.run_in_executor(
                _query_executor,
                lambda: predictive_agent.analyze(
                    context=context,
                    user_query=v1_predictive_user_query,
                    language=language,
                    schedule_filename=filename_clean,
                    reference_date=reference_date,
                    data_format=data_format,
                ),
            )

        predictive_json = predictive_result.get("predictive_json", None)
        predictive_status = predictive_result.get("status", "error")
        predictive_model = predictive_result.get("model", "")

        if isinstance(predictive_json, dict):
            delayed_rows = predictive_json.get("delayed_activities", [])
            if not isinstance(delayed_rows, list):
                delayed_rows = []
            critical_count = sum(1 for row in delayed_rows if row.get("priority") == "CRITICAL_NOW")
            important_count = sum(1 for row in delayed_rows if row.get("priority") == "IMPORTANT_NEXT")
            monitor_count = sum(1 for row in delayed_rows if row.get("priority") == "MONITOR")
            insight = predictive_json.setdefault("insight_data", {})
            overview = predictive_json.setdefault("schedule_overview", {})
            if row_count:
                insight["total_activities"] = row_count
                overview["total_activities"] = row_count
            insight["delayed_count"] = len(delayed_rows)
            insight["critical_count"] = critical_count
            insight["important_count"] = important_count
            insight["monitor_count"] = monitor_count
            overview["delayed_count"] = len(delayed_rows)

        _update_progress(analysis_id, "formatting", language)

        if format == "html" and predictive_json:
            response_text = format_predictive_v1_as_html(predictive_json, language)
        elif predictive_json:
            response_text = _json.dumps(predictive_json, ensure_ascii=False)
        else:
            response_text = predictive_result.get("predictive_insights", "")

        _update_progress(analysis_id, "complete", language)
        _schedule_progress_cleanup(analysis_id)

        elapsed = time.time() - start_time
        logger.info(f"=== VERSION 1.0 PREDICTIVE COMPLETE [{analysis_id}] ({elapsed:.1f}s) ===")

        # TL-5.5 (brief §17, §28): when context completeness is PARTIAL,
        # enumerate the omission in the response so the caller can act on
        # it. PASS is omitted (nothing to report) and BLOCK never reaches
        # this point (returned earlier via `_truncation_block_response`).
        response_payload: Dict[str, Any] = {
            "analysis_id": analysis_id,
            "response": response_text,
            "predictive_status": predictive_status,
            "predictive_model": predictive_model,
            "filename": filename,
            "reference_date": reference_date,
            "format": format,
            "version": "1.0",
            "processing_time_seconds": round(elapsed, 1),
        }
        if truncation_report is not None and truncation_report.decision == "PARTIAL":
            response_payload["context_completeness"] = truncation_report.to_dict()
        return response_payload

    except Exception as e:
        logger.error(f"Version 1.0 predictive dashboard failed: {e}", exc_info=True)
        _update_progress(analysis_id, "error", language, str(e))
        _schedule_progress_cleanup(analysis_id, delay=120)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/version-1.0/kemp/predictive")
async def version_1_kemp_predictive_dashboard(
    schedule: UploadFile = File(...),
    language: str = Form("da"),
    format: str = Form("html"),
    analysis_id: str = Form(None),
    data_format: str = Form("raw"),
):
    """Nova Insight Version 1.0 predictive decision dashboard — Kemp (green) variant.

    Identical analysis pipeline to ``/version-1.0/predictive``; only the
    rendered HTML's color palette differs (K&L green instead of Nova
    blue/teal). No adapter, agent, or data-shape changes.
    """
    import json as _json

    start_time = time.time()
    if not analysis_id:
        analysis_id = str(uuid.uuid4())[:12]

    filename = schedule.filename or "schedule.pdf"
    filename_clean = (
        filename.replace(".pdf", "").replace(".PDF", "")
        .replace(".csv", "").replace(".CSV", "")
        .replace(".xml", "").replace(".XML", "")
        .replace(".mpp", "").replace(".MPP", "")
    )
    reference_date = _extract_reference_date(filename)

    _update_progress(analysis_id, "received", language)
    logger.info(f"=== VERSION 1.0 KEMP PREDICTIVE REQUEST [{analysis_id}] ===")
    logger.info(f"Schedule: {filename} | Language: {language} | Format: {data_format} | Reference date: {reference_date or 'not found'}")

    if not _is_allowed_file(filename):
        _update_progress(analysis_id, "error", language)
        _schedule_progress_cleanup(analysis_id, delay=60)
        raise HTTPException(status_code=400, detail="Only PDF, CSV, Excel (.xlsx), Microsoft Project (.mpp), and MS Project XML (.xml) files are accepted")

    try:
        from src.version_1_0 import format_kemp_predictive_v1_as_html

        file_bytes = await schedule.read()
        _update_progress(analysis_id, "reading", language, f"{len(file_bytes) // 1024} KB")

        loop = asyncio.get_event_loop()
        is_csv_file = _is_csv(filename)
        is_mpp_file = _is_mpp(filename)
        is_mspdi_file = _is_mspdi(filename)

        # TL-5.5: `truncation_report` is set by the raw-text branches below.
        # The NUSF branch builds a structured JSON context (no byte-budget
        # gate applies), so it deliberately leaves the report as `None` —
        # the response builder checks for that and omits
        # `context_completeness` rather than publishing a meaningless one.
        truncation_report: Optional[TruncationReport] = None

        if data_format == "nusf":
            schedule_obj = await loop.run_in_executor(
                _query_executor,
                lambda: _run_nusf_pipeline(file_bytes, filename),
            )
            row_count = len(schedule_obj.activities)
            context = f"[NUSF structured facts for {row_count} activities — see structured context, not a text dump]"
        elif is_csv_file:
            context, truncation_report = _build_predictive_context_from_csv(file_bytes, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
            row_count = context.count("\n")
        elif is_mpp_file:
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: _process_mpp_to_chunks(file_bytes, filename),
            )
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
        elif is_mspdi_file:
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: _process_mspdi_to_chunks(file_bytes, filename),
            )
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)
        else:
            chunks = await loop.run_in_executor(
                _query_executor,
                lambda: process_pdf_binary(file_bytes, filename),
            )
            row_count = sum(c.get("metadata", {}).get("row_count", 0) for c in chunks)
            context, truncation_report = _build_predictive_context(chunks, filename_clean)
            if truncation_report.decision == "BLOCK":
                return _truncation_block_response(truncation_report, analysis_id, language, filename)

        _update_progress(analysis_id, "extracting", language, f"{row_count} activities")
        _update_progress(analysis_id, "analyzing", language, f"{row_count} activities")

        v1_predictive_user_query = (
            "Execute Nova Insight Version 1.0 predictive analysis: produce concise decision support, "
            "preserve real activity IDs, include location/phase/trade evidence when visible, avoid invented "
            "forecast values, and rank the top actions a project manager should take now."
        )
        if data_format == "nusf":
            # TL-5.4 (brief §4, §17): deterministic facts + narrative-only model call.
            predictive_result = await loop.run_in_executor(
                _query_executor,
                lambda: _run_nusf_predictive_analysis(
                    schedule_obj, filename_clean, v1_predictive_user_query, language, reference_date,
                ),
            )
        else:
            predictive_result = await loop.run_in_executor(
                _query_executor,
                lambda: predictive_agent.analyze(
                    context=context,
                    user_query=v1_predictive_user_query,
                    language=language,
                    schedule_filename=filename_clean,
                    reference_date=reference_date,
                    data_format=data_format,
                ),
            )

        predictive_json = predictive_result.get("predictive_json", None)
        predictive_status = predictive_result.get("status", "error")
        predictive_model = predictive_result.get("model", "")

        if isinstance(predictive_json, dict):
            delayed_rows = predictive_json.get("delayed_activities", [])
            if not isinstance(delayed_rows, list):
                delayed_rows = []
            critical_count = sum(1 for row in delayed_rows if row.get("priority") == "CRITICAL_NOW")
            important_count = sum(1 for row in delayed_rows if row.get("priority") == "IMPORTANT_NEXT")
            monitor_count = sum(1 for row in delayed_rows if row.get("priority") == "MONITOR")
            insight = predictive_json.setdefault("insight_data", {})
            overview = predictive_json.setdefault("schedule_overview", {})
            if row_count:
                insight["total_activities"] = row_count
                overview["total_activities"] = row_count
            insight["delayed_count"] = len(delayed_rows)
            insight["critical_count"] = critical_count
            insight["important_count"] = important_count
            insight["monitor_count"] = monitor_count
            overview["delayed_count"] = len(delayed_rows)

        _update_progress(analysis_id, "formatting", language)

        if format == "html" and predictive_json:
            response_text = format_kemp_predictive_v1_as_html(predictive_json, language)
        elif predictive_json:
            response_text = _json.dumps(predictive_json, ensure_ascii=False)
        else:
            response_text = predictive_result.get("predictive_insights", "")

        _update_progress(analysis_id, "complete", language)
        _schedule_progress_cleanup(analysis_id)

        elapsed = time.time() - start_time
        logger.info(f"=== VERSION 1.0 KEMP PREDICTIVE COMPLETE [{analysis_id}] ({elapsed:.1f}s) ===")

        # TL-5.5 (brief §17, §28): when context completeness is PARTIAL,
        # enumerate the omission in the response so the caller can act on
        # it. PASS is omitted (nothing to report) and BLOCK never reaches
        # this point (returned earlier via `_truncation_block_response`).
        response_payload: Dict[str, Any] = {
            "analysis_id": analysis_id,
            "response": response_text,
            "predictive_status": predictive_status,
            "predictive_model": predictive_model,
            "filename": filename,
            "reference_date": reference_date,
            "format": format,
            "version": "1.0-kemp",
            "processing_time_seconds": round(elapsed, 1),
        }
        if truncation_report is not None and truncation_report.decision == "PARTIAL":
            response_payload["context_completeness"] = truncation_report.to_dict()
        return response_payload

    except Exception as e:
        logger.error(f"Version 1.0 Kemp predictive dashboard failed: {e}", exc_info=True)
        _update_progress(analysis_id, "error", language, str(e))
        _schedule_progress_cleanup(analysis_id, delay=120)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/version-1.0/localize")
async def version_1_localize_dashboard(
    html: str = Form(...),
    language: str = Form("da"),
):
    """Re-render an existing Version 1.0 dashboard HTML in the requested language.

    This avoids running the full analysis twice. The route extracts the
    deterministic dashboard payload embedded in the returned HTML and renders
    the same health or predictive dashboard shell with localized labels.
    """
    start_time = time.time()
    try:
        from src.version_1_0 import localize_v1_html

        response_text = localize_v1_html(html, language)
        elapsed = time.time() - start_time

        return {
            "response": response_text,
            "format": "html",
            "language": "da" if str(language).lower().startswith("da") else "en",
            "version": "1.0",
            "processing_time_seconds": round(elapsed, 3),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Version 1.0 localization failed: {e}", exc_info=True)

# ── Source Document & Viewer Routes (TL-9.1, Brief §24) ──────────────────────
@app.post("/source-document/highlight")
async def highlight_source_document(
    page_number: int = Form(...),
    bounding_box: Optional[str] = Form(None),
    pdf_file: UploadFile = File(...),
):
    """Render a target page of a source PDF with bounding box highlight."""
    try:
        from src.trust.source_viewer import highlight_pdf_page
        pdf_bytes = await pdf_file.read()
        bbox = None
        if bounding_box:
            try:
                if isinstance(bounding_box, str):
                    s = bounding_box.strip()
                    if s.startswith("[") and s.endswith("]"):
                        s = s[1:-1]
                    bbox = [float(x.strip()) for x in s.split(",") if x.strip()]
                elif isinstance(bounding_box, list):
                    bbox = [float(x) for x in bounding_box]
            except Exception as parse_err:
                logger.warning(f"Could not parse bounding_box {bounding_box!r}: {parse_err}")
                bbox = None
        png_bytes = highlight_pdf_page(pdf_bytes, page_number, bbox)
        return Response(content=png_bytes, media_type="image/png")
    except (ValueError, IndexError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Highlight source document failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/source-document/{session_id}/{schedule_role}/page/{page_number}")
async def get_session_source_document_page(
    session_id: str,
    schedule_role: str,
    page_number: int,
    bbox: Optional[str] = None,
):
    """Render a highlighted page from a cached session schedule."""
    if schedule_role not in ("old", "new", "single"):
        raise HTTPException(status_code=400, detail="Invalid schedule_role: must be old, new, or single")

    cache_key = f"{session_id}:{schedule_role}"
    pdf_bytes = _source_file_cache.get(cache_key)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Source document not found in session cache")

    if not pdf_bytes.startswith(b"%PDF"):
        # Non-paginated documents degrade honestly (Do-not rule: never fabricate page numbers)
        raise HTTPException(status_code=400, detail="Source document is not a paginated PDF")

    parsed_bbox = None
    if bbox:
        try:
            if isinstance(bbox, str):
                s = bbox.strip()
                if s.startswith("[") and s.endswith("]"):
                    s = s[1:-1]
                parsed_bbox = [float(x.strip()) for x in s.split(",") if x.strip()]
            elif isinstance(bbox, list):
                parsed_bbox = [float(x) for x in bbox]
        except Exception:
            parsed_bbox = None

    from src.trust.source_viewer import highlight_pdf_page
    try:
        png_bytes = highlight_pdf_page(pdf_bytes, page_number, parsed_bbox)
        return Response(content=png_bytes, media_type="image/png")
    except (ValueError, IndexError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/source-document/activity-detail")
async def get_activity_detail_endpoint(payload: dict):
    """Return Brief §24 target activity detail data and rendered HTML."""
    from src.trust.source_viewer import build_activity_detail, render_activity_detail_panel
    activity = payload.get("activity", {})
    old_activity = payload.get("old_activity")
    match_result = payload.get("match_result")
    new_provenance = payload.get("new_provenance")
    old_provenance = payload.get("old_provenance")
    language = payload.get("language", "en")

    detail = build_activity_detail(
        activity,
        old_activity,
        match_result,
        new_provenance=new_provenance,
        old_provenance=old_provenance,
        language=language,
    )
    html = render_activity_detail_panel(detail, language=language)
    return {
        "success": True,
        "detail": detail.model_dump(),
        "html": html,
    }


# ── Audit Trail Routes (TL-9.2, Brief §40) ───────────────────────────────────
@app.get("/audit-trail/{analysis_id}")
async def get_audit_trail_endpoint(analysis_id: str):
    """Retrieve Brief §40 audit reconstruction trail for an analysis."""
    from src.trust.audit import audit_store

    trail = audit_store.get(analysis_id)
    if not trail:
        raise HTTPException(status_code=404, detail="Audit trail not found")
    return {
        "success": True,
        "is_complete": trail.is_complete(),
        "integrity_verified": trail.verify_integrity(),
        "trail": trail.model_dump(),
        "reconstruction": trail.reconstruct_answer(),
    }


# ── Trust Metrics KPIs Routes (TL-9.4, Brief §38, §49) ──────────────────────
@app.get("/trust-metrics/latest")
async def get_latest_metrics_endpoint(
    project_id: Optional[str] = None,
    company_id: Optional[str] = None,
):
    """Retrieve the latest Brief §38 trust KPIs snapshot."""
    from src.trust.metrics import metrics_store
    snap = metrics_store.get_latest(project_id=project_id, company_id=company_id)
    if not snap:
        raise HTTPException(status_code=404, detail="No metrics recorded yet")
    return {"success": True, "snapshot": snap.to_summary_dict()}


@app.get("/trust-metrics/trend/{metric_name}")
async def get_metrics_trend_endpoint(
    metric_name: str,
    project_id: Optional[str] = None,
    company_id: Optional[str] = None,
    limit: int = 50,
):
    """Query time-series trend points for a specific KPI (Brief §49)."""
    from src.trust.metrics import ALL_TEN_BRIEF_38_METRICS, metrics_store
    if metric_name not in ALL_TEN_BRIEF_38_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric '{metric_name}'. Valid metrics: {list(ALL_TEN_BRIEF_38_METRICS)}",
        )
    trend = metrics_store.get_metric_trend(
        metric_name=metric_name,
        project_id=project_id,
        company_id=company_id,
        limit=limit,
    )
    return {
        "success": True,
        "metric_name": metric_name,
        "points_count": len(trend),
        "trend": trend,
    }


@app.get("/trust-metrics/history")
async def get_metrics_history_endpoint(
    project_id: Optional[str] = None,
    company_id: Optional[str] = None,
    limit: int = 50,
):
    """Retrieve metrics snapshot history matching tenant filters."""
    from src.trust.metrics import metrics_store
    history = metrics_store.get_history(
        project_id=project_id, company_id=company_id, limit=limit
    )
    return {
        "success": True,
        "count": len(history),
        "snapshots": [s.to_summary_dict() for s in history],
    }


# ── Trust Center Routes (TL-9.5, Brief §43) ──────────────────────────────────
@app.get("/trust-center/summary")
async def get_trust_center_summary_endpoint(
    company_id: Optional[str] = None,
    locale: str = "da",
):
    """Retrieve Brief §43 Trust Center overview with defined denominators."""
    from src.trust.trust_center import build_trust_center_overview
    overview = build_trust_center_overview(company_id=company_id, locale=locale)
    return {
        "success": True,
        "trust_center": overview.model_dump(),
    }


@app.get("/trust-center/report")
async def get_trust_center_report_endpoint(
    company_id: Optional[str] = None,
    locale: str = "da",
    format: str = "markdown",
):
    """Export the Brief §43 Verification Report in Markdown or JSON format."""
    from src.trust.trust_center import build_trust_center_overview, generate_verification_report
    overview = build_trust_center_overview(company_id=company_id, locale=locale)
    report = generate_verification_report(overview, format=format)
    if format.lower() == "markdown":
        return Response(content=report, media_type="text/markdown; charset=utf-8")
    return {
        "success": True,
        "report": report,
    }


# Dependency injection keeps ingestion/ free of src/ imports.
# All downstream objects (vector_store_manager, predictive_agent, etc.) are
# wired here in src/main.py and passed into the router at startup.
# Existing /upload, /query, /predictive routes above are NOT modified.
from ingestion.routes.ingestion import (
    router as _v2_router,
    configure as _v2_configure,
    RouterDependencies,
)
from src.vector_store import vector_store_manager as _vsm
from src.database import save_session_metadata as _save_session_metadata

from src.database import get_session_metadata as _get_session_metadata

_v2_configure(RouterDependencies(
    vector_store_manager=_vsm,
    save_session_metadata=_save_session_metadata,
    rag_agent=rag_agent,
    format_comparison_html=format_response_as_html,
    get_session_metadata=_get_session_metadata,
))
app.include_router(_v2_router, prefix="/v2")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
