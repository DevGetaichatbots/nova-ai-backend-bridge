# backend/ingestion/recognition/

## Responsibility
Heuristic + AI-fallback field/entity recognition for ingested project data. This module maps raw column headers from construction schedule files (MS Project, Tactplan, Plandisc, structured tables) to NUSF semantic roles — a standardised set of field names (`name`, `planned_start`, `planned_finish`, `duration`, `wbs_code`, `predecessors`, etc.) that downstream transformers and loaders consume.

## Design
Rule-based heuristics with an AI fallback chain. The primary class `HeuristicRecognizer` uses a bilingual (Danish/English) `TOKEN_MAP` (defined in `heuristics.py`) and Jaro-Winkler fuzzy string matching (`_jaro_winkler`, threshold 0.85) to score each raw header against candidate tokens per semantic role. It also classifies the source schedule format via `_detect_match_key`, returning one of `"tbs"`, `"id"`, `"entydigt_id"`, `"name_location"`, or `"row_index"`. When critical fields (`name`, `planned_start`, `planned_finish` — the `CRITICAL_FIELDS` set) cannot be resolved, the `RecognitionResult.ai_needed` flag is set and downstream code invokes `AIFallbackRecognizer`, which issues a JSON-only chat completion to Azure OpenAI (gpt-4.1 default). The AI results are cached in-memory (`_SESSION_CACHE`) by an MD5 hash of sorted, normalised headers (`_cache_key`).

## Data & Control Flow
1. `HeuristicRecognizer.recognize(headers)` iterates every raw header against every `TOKEN_MAP` entry via `_best_match` (exact match wins at score 1.0; otherwise Jaro-Winkler at ≥0.85).  
2. Builds `column_map` (semantic role → original header) and `score_map`.  
3. `_detect_match_key` classifies the schedule format from the lowercased headers and resolved column map.  
4. `ai_needed` is set if any of `CRITICAL_FIELDS` are absent from `column_map`; confidence is the fraction of critical fields mapped.  
5. Downstream code checks `result.ai_needed`; if true, calls `AIFallbackRecognizer.recognize(headers)` to augment the map via Azure OpenAI, with responses cached per session by sorted-header MD5 digest.

## Integration Points
- **Dependencies**: Azure OpenAI SDK (`openai.AzureOpenAI`) in `ai_fallback.py`; environment variables `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`.
- **Consumers**: Upstream `ingestion/` subdirectories (NUSF transformer / loader) that require a resolved semantic column map before transforming raw schedule rows into the canonical NUSF structure.

## Public Surface
- `HeuristicRecognizer` (`heuristics.py`) — Primary recogniser; matches headers to NUSF semantic roles via token dictionary and Jaro-Winkler fuzzy matching. Entry point: `recognize(headers: List[str]) -> RecognitionResult`.
- `AIFallbackRecognizer` (`ai_fallback.py`) — Secondary recogniser; invokes Azure OpenAI when heuristics cannot resolve critical fields. Entry point: `recognize(headers: List[str]) -> Optional[Dict[str, str]]`.
- `RecognitionResult` (`heuristics.py`) — Data object holding `column_map`, `match_key`, `format_label`, `ai_needed`, and `confidence`.
