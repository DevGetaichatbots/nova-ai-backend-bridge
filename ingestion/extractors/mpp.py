"""
MPP Extractor
=============
Reads Microsoft Project .mpp files using the MPXJ library (v16+) via JPype.

Package location: org.mpxj (moved from net.sf.mpxj in MPXJ v16)
Reader:           org.mpxj.reader.UniversalProjectReader
Task getters:     getName(), getStart(), getFinish(), getDuration(),
                  getPercentageComplete(), getWBS(), getID(),
                  getPredecessors(), getResourceAssignments()

JVM lifecycle:
  JPype starts a JVM once per process. A module-level threading.Lock +
  _JVM_STARTED flag guarantee the JVM is initialised exactly once under
  concurrent requests. The JVM is started with an explicit classpath built
  from the mpxj package's lib/ directory — relying solely on addClassPath()
  before startJVM() is not reliable across JPype versions.

Self-registers to ExtractorRegistry under "MPP" source system on import.
"""
import glob
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ingestion.extractors.base import BaseExtractor
from ingestion.extractors.registry import ExtractorRegistry

logger = logging.getLogger(__name__)

_JVM_STARTED = False
_JVM_LOCK = threading.Lock()


def _find_mpxj_jars() -> List[str]:
    """Locate the mpxj lib/ directory and return all JAR paths."""
    try:
        import mpxj as _mpxj_pkg
        lib_dir = os.path.join(os.path.dirname(_mpxj_pkg.__file__), "lib")
        jars = glob.glob(os.path.join(lib_dir, "*.jar"))
        if jars:
            logger.debug(f"Found {len(jars)} MPXJ JARs in {lib_dir}")
            return jars
    except ImportError:
        pass
    return []


def _ensure_jvm() -> None:
    """Start the JVM exactly once with the MPXJ classpath."""
    global _JVM_STARTED
    if _JVM_STARTED:
        return
    with _JVM_LOCK:
        if _JVM_STARTED:
            return
        try:
            import jpype
            if not jpype.isJVMStarted():
                jars = _find_mpxj_jars()
                if not jars:
                    raise RuntimeError(
                        "No MPXJ JARs found. Ensure the 'mpxj' Python package is "
                        "installed (add 'mpxj' to pyproject.toml dependencies)."
                    )
                jpype.startJVM(convertStrings=True, classpath=jars)
                logger.info(
                    f"JVM started for MPXJ extraction "
                    f"(path: {jpype.getDefaultJVMPath()}, JARs: {len(jars)})"
                )
            else:
                logger.debug("JVM already running — reusing existing instance")
            _JVM_STARTED = True
        except ImportError as exc:
            raise RuntimeError(
                "JPype1 is not installed. Add 'JPype1' to pyproject.toml dependencies."
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Failed to start JVM. Ensure 'jdk17' is listed in Nix packages in "
                f".replit and the server has been restarted. Detail: {exc}"
            ) from exc


def _java_date_to_str(value) -> str:
    """
    Convert a Java LocalDateTime / Date to 'DD-MM-YYYY'.
    MPXJ v16 returns LocalDateTime from getStart()/getFinish().
    Falls back to .toString() parsing if the exact Java type varies.
    """
    if value is None:
        return ""
    try:
        s = str(value)
        if "T" in s:
            dt = datetime.fromisoformat(s.split("T")[0])
            return dt.strftime("%d-%m-%Y")
        dt = datetime.fromisoformat(s[:10])
        return dt.strftime("%d-%m-%Y")
    except Exception:
        pass
    try:
        millis = int(value.getTime())
        dt = datetime.fromtimestamp(millis / 1000.0)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return str(value)


def _duration_to_str(value) -> str:
    """Convert an org.mpxj.Duration object to a human-readable string."""
    if value is None:
        return ""
    try:
        amount = float(str(value.getDuration()))
        units = str(value.getUnits())
        upper = units.upper()
        if "DAY" in upper:
            return f"{amount:.1f}d"
        if "WEEK" in upper:
            return f"{amount:.1f}w"
        if "HOUR" in upper:
            return f"{amount:.1f}h"
        return f"{amount:.1f}"
    except Exception:
        return str(value)


def _duration_to_days(value) -> str:
    """Convert an org.mpxj.Duration object to working-day float text."""
    if value is None:
        return ""
    try:
        amount = float(str(value.getDuration()))
        units = str(value.getUnits()).upper()
        if "DAY" in units:
            days = amount
        elif "WEEK" in units:
            days = amount * 5.0
        elif "HOUR" in units:
            days = amount / 8.0
        elif "MINUTE" in units:
            days = amount / 480.0
        else:
            days = amount
        return f"{days:.1f}"
    except Exception:
        return ""


def _critical_to_str(task) -> str:
    for method_name in ("getCritical", "isCritical"):
        try:
            method = getattr(task, method_name)
            value = method()
            if value is None:
                continue
            return "1" if str(value).strip().lower() in ("true", "1", "yes") else "0"
        except Exception:
            continue
    return ""


def _total_slack_to_str(task) -> str:
    for method_name in ("getTotalSlack", "getTotalFloat"):
        try:
            method = getattr(task, method_name)
            value = method()
            if value is None:
                continue
            return _duration_to_days(value)
        except Exception:
            continue
    return ""


def _pct_to_str(value) -> str:
    """Convert a Java Number percentage to a plain integer string."""
    if value is None:
        return "0"
    try:
        return str(int(float(str(value))))
    except Exception:
        return "0"


def _safe(value) -> str:
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:
        return ""


class MPPExtractor(BaseExtractor):
    """
    Extracts schedule task data from Microsoft Project .mpp files.

    Output headers mirror the Danish/English column names used by the
    normalisation engine so the HeuristicRecognizer maps them without
    needing an AI fallback.
    """

    HEADERS: List[str] = [
        "ID",
        "Aktivitetsnavn",
        "Startdato",
        "Slutdato",
        "Varighed",
        "Fuldført %",
        "WBS",
        "Forgænger-ID",
        "Ressourcer",
        "Critical",
        "TotalSlack",
    ]

    def extract(self, file_path: Path) -> Dict[str, Any]:
        return self.extract_from_bytes(file_path.read_bytes(), file_path.name)

    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        _ensure_jvm()

        suffix = Path(filename).suffix or ".mpp"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            rows = self._read_mpp(tmp_path, filename)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        raw_text = "\n".join(
            [";".join(self.HEADERS)] + [";".join(row) for row in rows]
        )

        logger.info(f"[{filename}] MPP extracted: {len(rows)} task rows")

        return {
            "source_system": self.source_system(),
            "headers": list(self.HEADERS),
            "rows": rows,
            "file_name": filename,
            "raw_text": raw_text,
        }

    def _read_mpp(self, file_path_str: str, filename: str) -> List[List[str]]:
        import jpype

        try:
            UPR = jpype.JClass("org.mpxj.reader.UniversalProjectReader")
        except Exception as exc:
            raise RuntimeError(
                "Could not load org.mpxj.reader.UniversalProjectReader. "
                "Ensure the 'mpxj' package (v16+) is installed and jdk17 is available. "
                f"Detail: {exc}"
            ) from exc

        try:
            project = UPR().read(file_path_str)
        except Exception as exc:
            raise ValueError(
                f"MPXJ could not read '{filename}'. "
                f"Ensure the file is a valid .mpp format. Detail: {exc}"
            ) from exc

        rows: List[List[str]] = []
        skipped = 0
        for task in project.getTasks():
            try:
                task_id = task.getID()
                if task_id is None:
                    skipped += 1
                    continue
                name = _safe(task.getName())
                if not name:
                    skipped += 1
                    continue

                row = [
                    str(int(task_id)),
                    name,
                    _java_date_to_str(task.getStart()),
                    _java_date_to_str(task.getFinish()),
                    _duration_to_str(task.getDuration()),
                    _pct_to_str(task.getPercentageComplete()),
                    _safe(task.getWBS()),
                    self._predecessors_str(task),
                    self._resources_str(task),
                    _critical_to_str(task),
                    _total_slack_to_str(task),
                ]
                rows.append(row)
            except Exception as exc:
                logger.warning(f"[{filename}] Skipping task (error): {exc}")
                skipped += 1
                continue

        if skipped > 0:
            logger.info(
                f"[{filename}] MPP extraction: {len(rows)} tasks extracted, "
                f"{skipped} skipped (null ID, blank name, or parse error)"
            )
        return rows

    def _predecessors_str(self, task) -> str:
        try:
            preds = task.getPredecessors()
            if not preds:
                return ""
            ids = []
            for rel in preds:
                try:
                    pred_task = rel.getPredecessorTask()
                    if pred_task is not None:
                        pred_id = pred_task.getID()
                        if pred_id is not None:
                            ids.append(str(int(pred_id)))
                except Exception:
                    continue
            return ";".join(ids)
        except Exception:
            return ""

    def _resources_str(self, task) -> str:
        try:
            assignments = task.getResourceAssignments()
            if not assignments:
                return ""
            names = []
            for assignment in assignments:
                try:
                    res = assignment.getResource()
                    if res is not None:
                        res_name = res.getName()
                        if res_name:
                            names.append(_safe(res_name))
                except Exception:
                    continue
            return ";".join(names[:3])
        except Exception:
            return ""

    def source_system(self) -> str:
        return "MPP"


_mpp_extractor_instance = MPPExtractor()
ExtractorRegistry.register("MPP", _mpp_extractor_instance)
