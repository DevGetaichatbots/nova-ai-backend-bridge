"""
MSPDI Extractor
===============
Reads Microsoft Project XML files in MSPDI format
(namespace http://schemas.microsoft.com/project).

This is the standard XML export from Microsoft Project (Save As → XML) and
from tools such as Aspose.Tasks. It is a pure-Python implementation that uses
only the stdlib xml.etree.ElementTree module — no JVM or extra packages needed.

Key structural notes from the MSPDI schema:
  - <Tasks>/<Task>   — one element per task row
  - <UID>            — stable internal ID used for cross-references
  - <ID>             — display row number shown in MS Project's ID column
  - <Start>/<Finish> — ISO datetime e.g. "2024-07-29T08:00:00"
  - <Duration>       — ISO 8601 duration  e.g. "PT584H0M0S"
  - <PercentComplete> — integer 0-100
  - <WBS>            — e.g. "1.3"
  - <PredecessorLink>/<PredecessorUID> — references the UID (not ID) of the
    predecessor task; converted to display ID via a UID→ID lookup map
  - <ExtendedAttributes> at project level maps FieldID → alias ("ansvar" etc.)
  - <Resources>/<Resource> and <Assignments>/<Assignment> provide resource names
    per task; "ansvar" (Text1) extended attribute is used as a fallback

Duration conversion uses 8 working hours per day (flat, same as MPPExtractor).

Self-registers to ExtractorRegistry under "MSPDI" source system on import.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ingestion.extractors.base import BaseExtractor
from ingestion.extractors.registry import ExtractorRegistry

logger = logging.getLogger(__name__)

_NS = "http://schemas.microsoft.com/project"
_P = f"{{{_NS}}}"

_DURATION_RE = re.compile(
    r"PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?$"
)


def _t(tag: str) -> str:
    """Prepend the MSPDI namespace prefix to a bare tag name."""
    return f"{_P}{tag}"


def _text(element: Optional[ET.Element], tag: str, default: str = "") -> str:
    """Return stripped text of a child element, or default if absent."""
    child = element.find(_t(tag))
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _parse_iso_date(s: str) -> str:
    """
    Convert an MSPDI datetime string to 'DD-MM-YYYY'.
    Input examples: "2024-07-29T08:00:00", "2024-07-29"
    """
    if not s:
        return ""
    try:
        date_part = s.split("T")[0]
        dt = datetime.fromisoformat(date_part)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return ""


def _parse_iso_duration(s: str) -> str:
    """
    Convert an ISO 8601 duration string to working-day notation.
    Uses 8 working hours per day.
    Examples:
      "PT584H0M0S" → "73.0d"
      "PT40H0M0S"  → "5.0d"
      "PT0H0M0S"   → ""  (zero duration)
    """
    if not s:
        return ""
    m = _DURATION_RE.match(s.strip())
    if not m:
        return s
    hours = float(m.group(1) or 0)
    minutes = float(m.group(2) or 0)
    seconds = float(m.group(3) or 0)
    total_hours = hours + minutes / 60.0 + seconds / 3600.0
    if total_hours < 0.001:
        return ""
    days = total_hours / 8.0
    return f"{days:.1f}d"


class MspdiExtractor(BaseExtractor):
    """
    Extracts schedule task data from MSPDI-format Microsoft Project XML files.

    Output headers are identical to MPPExtractor so the normalisation engine
    and both agents receive data in the same compact CSV format regardless of
    whether the source was .mpp or .xml.
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
    ]

    def extract(self, file_path: Path) -> Dict[str, Any]:
        return self.extract_from_bytes(file_path.read_bytes(), file_path.name)

    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        try:
            root = ET.fromstring(file_bytes)
        except ET.ParseError as exc:
            raise ValueError(
                f"'{filename}' is not valid XML. "
                f"Ensure the file is a Microsoft Project XML export. Detail: {exc}"
            ) from exc

        if root.tag != _t("Project"):
            raise ValueError(
                f"'{filename}' does not appear to be an MSPDI file. "
                f"Root element is '{root.tag}'; expected "
                f"'{{{_NS}}}Project'."
            )

        rows = self._parse_tasks(root, filename)

        raw_text = "\n".join(
            [";".join(self.HEADERS)] + [";".join(row) for row in rows]
        )

        logger.info(f"[{filename}] MSPDI extracted: {len(rows)} task rows")

        return {
            "source_system": self.source_system(),
            "headers": list(self.HEADERS),
            "rows": rows,
            "file_name": filename,
            "raw_text": raw_text,
        }

    def _parse_tasks(self, root: ET.Element, filename: str) -> List[List[str]]:
        ansvar_field_id = self._find_ansvar_field_id(root)
        resource_map = self._build_resource_map(root)
        assignment_map = self._build_assignment_map(root, resource_map)
        uid_to_id = self._build_uid_to_id(root)

        tasks_el = root.find(_t("Tasks"))
        if tasks_el is None:
            logger.warning(f"[{filename}] No <Tasks> element found in MSPDI")
            return []

        rows: List[List[str]] = []
        skipped = 0

        for task_el in tasks_el.findall(_t("Task")):
            try:
                if _text(task_el, "IsNull") == "1":
                    skipped += 1
                    continue

                uid_str = _text(task_el, "UID")
                if uid_str == "0":
                    skipped += 1
                    continue

                name = _text(task_el, "Name")
                if not name:
                    skipped += 1
                    continue

                display_id = _text(task_el, "ID")

                row = [
                    display_id,
                    name,
                    _parse_iso_date(_text(task_el, "Start")),
                    _parse_iso_date(_text(task_el, "Finish")),
                    _parse_iso_duration(_text(task_el, "Duration")),
                    _text(task_el, "PercentComplete", "0"),
                    _text(task_el, "WBS"),
                    self._predecessors_str(task_el, uid_to_id),
                    self._resources_str(task_el, uid_str, assignment_map,
                                        ansvar_field_id),
                ]
                rows.append(row)
            except Exception as exc:
                logger.warning(f"[{filename}] Skipping task (error): {exc}")
                skipped += 1
                continue

        if skipped > 0:
            logger.info(
                f"[{filename}] MSPDI extraction: {len(rows)} tasks extracted, "
                f"{skipped} skipped (null, project summary, blank name, or parse error)"
            )
        return rows

    def _find_ansvar_field_id(self, root: ET.Element) -> Optional[str]:
        """
        Find the FieldID for the custom extended attribute aliased "ansvar".
        The project owner/responsibility field is commonly stored as Text1
        with FieldID 188743731 and alias "ansvar".
        Returns the FieldID string, or None if not found.
        """
        ea_root = root.find(_t("ExtendedAttributes"))
        if ea_root is None:
            return None
        for ea in ea_root.findall(_t("ExtendedAttribute")):
            alias = _text(ea, "Alias").lower()
            if alias in ("ansvar", "responsibility", "owner"):
                fid = _text(ea, "FieldID")
                if fid:
                    logger.debug(f"Found ansvar field ID: {fid}")
                    return fid
        return None

    def _build_resource_map(self, root: ET.Element) -> Dict[str, str]:
        """Build {resource_uid: resource_name} from <Resources>."""
        result: Dict[str, str] = {}
        res_root = root.find(_t("Resources"))
        if res_root is None:
            return result
        for res in res_root.findall(_t("Resource")):
            uid = _text(res, "UID")
            name = _text(res, "Name")
            if uid and name and uid != "0":
                result[uid] = name
        return result

    def _build_assignment_map(
        self, root: ET.Element, resource_map: Dict[str, str]
    ) -> Dict[str, List[str]]:
        """Build {task_uid: [resource_name, ...]} from <Assignments>."""
        result: Dict[str, List[str]] = {}
        asgn_root = root.find(_t("Assignments"))
        if asgn_root is None:
            return result
        for asgn in asgn_root.findall(_t("Assignment")):
            task_uid = _text(asgn, "TaskUID")
            res_uid = _text(asgn, "ResourceUID")
            if not task_uid or res_uid in ("", "0", "-65535"):
                continue
            res_name = resource_map.get(res_uid)
            if res_name:
                result.setdefault(task_uid, [])
                if res_name not in result[task_uid]:
                    result[task_uid].append(res_name)
        return result

    def _build_uid_to_id(self, root: ET.Element) -> Dict[str, str]:
        """
        Build {uid: display_id} from <Tasks>.
        Used to resolve PredecessorUID → display ID for the output column.
        """
        uid_to_id: Dict[str, str] = {}
        tasks_el = root.find(_t("Tasks"))
        if tasks_el is None:
            return uid_to_id
        for task_el in tasks_el.findall(_t("Task")):
            uid = _text(task_el, "UID")
            id_ = _text(task_el, "ID")
            if uid and id_:
                uid_to_id[uid] = id_
        return uid_to_id

    def _predecessors_str(
        self, task_el: ET.Element, uid_to_id: Dict[str, str]
    ) -> str:
        """
        Extract predecessor display IDs from all <PredecessorLink> children.
        <PredecessorUID> holds the UID — resolve to display ID via lookup.
        """
        ids: List[str] = []
        for link in task_el.findall(_t("PredecessorLink")):
            pred_uid = _text(link, "PredecessorUID")
            if pred_uid:
                display_id = uid_to_id.get(pred_uid, pred_uid)
                ids.append(display_id)
        return ";".join(ids)

    def _resources_str(
        self,
        task_el: ET.Element,
        task_uid: str,
        assignment_map: Dict[str, List[str]],
        ansvar_field_id: Optional[str],
    ) -> str:
        """
        Resolve resource names from the assignment map.
        If no assignment exists, fall back to the "ansvar" extended attribute value.
        Returns up to 3 resource names joined by semicolons.
        """
        resources = assignment_map.get(task_uid, [])
        if resources:
            return ";".join(resources[:3])

        if ansvar_field_id:
            for ea in task_el.findall(_t("ExtendedAttribute")):
                if _text(ea, "FieldID") == ansvar_field_id:
                    val = _text(ea, "Value")
                    if val:
                        return val
        return ""

    def source_system(self) -> str:
        return "MSPDI"


_mspdi_extractor_instance = MspdiExtractor()
ExtractorRegistry.register("MSPDI", _mspdi_extractor_instance)
