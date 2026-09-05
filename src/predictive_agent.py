from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam
from src.config import settings
from typing import List
from datetime import datetime, date, timezone, timedelta
import json
import logging

from src.trust.vocabulary import EvidenceClass, TrustState
from src.trust.claims import build_field_claim_kinds, verify_narrative
from src.trust.response_contract import (
    AgentResponse,
    GatePolicy,
    detect_no_answer,
    is_causal_question,
    merge_inferences,
    validate_agent_response,
)

logger = logging.getLogger(__name__)

NOVA_INSIGHT_SCHEMA = {
    "name": "nova_insight_report",
    "strict": True,
    "schema": {
        "type": "object",
        "required": [
            "predictive_snapshot",
            "predictive_biggest_risk",
            "executive_actions",
            "management_conclusion",
            "schedule_overview",
            "delayed_activities",
            "root_cause_analysis",
            "downstream_consequences",
            "priority_actions",
            "resource_assessment",
            "forcing_assessment",
            "summary_by_area",
            "insight_data"
        ],
        "additionalProperties": False,
        "properties": {
            "predictive_snapshot": {
                "type": "object",
                "description": "A plain-language predictive summary synthesised from the full analysis. Answers the 5 key executive questions in under 10 seconds of reading.",
                "required": ["what_will_happen", "estimated_delay_impact", "confidence_level", "confidence_basis", "main_delay_drivers"],
                "additionalProperties": False,
                "properties": {
                    "what_will_happen": {
                        "type": "string",
                        "description": "When delayed_count > 0: ONE concrete sentence starting with 'If no action is taken, ...' — state the expected total delay window and the primary cause. Example: 'If no action is taken, your project is expected to be delayed by 4–8 months due to unresolved coordination and design dependencies.' When delayed_count = 0 (no confirmed delays, only structural changes): do NOT fabricate a delay window. Instead describe the structural risk: 'Large-scale restructuring introduces elevated coordination risk — [N] tasks added and [M] removed across [disciplines] — validation of new dependency links is required before schedule impact can be confirmed.'"
                    },
                    "estimated_delay_impact": {
                        "type": "string",
                        "description": "When delayed_count > 0: Concise delay estimate derived from most_overdue_days and cascade risk. Format: '+N weeks' or '+N–M months'. Examples: '+6 weeks', '+3–5 months', '+8–12 weeks'. When delayed_count = 0: use 'Requires validation' — do NOT invent a delay number when no overdue activities exist."
                    },
                    "confidence_level": {
                        "type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW"],
                        "description": "HIGH = clear root causes with concrete days, full schedule data available. MEDIUM = some ambiguity in root cause chain or partial data. LOW = sparse data, unstructured format, or fewer than 5 delayed activities."
                    },
                    "confidence_basis": {
                        "type": "string",
                        "description": "One sentence explaining why the confidence level was assigned. Example: 'Based on 28 delayed activities with clear root cause chains across 3 disciplines.' or 'Based on partial data — schedule has no predecessor columns, dependency chains inferred.'",
                    },
                    "main_delay_drivers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Exactly 3 short bullet strings summarising the top delay categories. Each ≤15 words. Reference real task types and counts. Example: ['12 coordination bottlenecks blocking cross-discipline handoffs', '6 unresolved bygherre decisions stalling design input', '8 production tasks overdue in Omr. 2 and Omr. 3']"
                    }
                }
            },
            "predictive_biggest_risk": {
                "type": "object",
                "description": "The single highest-impact root cause — rendered as a 3-part risk card at the top of the report.",
                "required": ["risk_title", "will_block", "prevent_action_now"],
                "additionalProperties": False,
                "properties": {
                    "risk_title": {
                        "type": "string",
                        "description": "≤15 words naming the specific task or issue. Must include task ID and concrete overdue figure. Example: 'Task ID 41 — coordination milestone 47 days overdue, blocking all EL and VVS trades.' NEVER vague ('multiple delays exist'). NEVER omit the ID."
                    },
                    "will_block": {
                        "type": "string",
                        "description": "One sentence identifying the downstream consequence if this risk is not resolved. Example: 'Unresolved, this will delay electrical and HVAC installation across Omr. 2 and Omr. 3 by at least 6–8 weeks.' Reference real disciplines/areas."
                    },
                    "prevent_action_now": {
                        "type": "string",
                        "description": "≤10-word imperative verb phrase — the single action that prevents this risk. Match the WHAT style rule: start with a verb, name the responsible party or task. Example: 'Escalate ID 41 coordination meeting to project director today.' FORBIDDEN: 'monitor', 'consider', 'review', 'look into'."
                    }
                }
            },
            "executive_actions": {
                "type": "array",
                "description": "TOP 3 most critical actions the project manager must take IMMEDIATELY. Not analysis — direct, concrete instructions. Each action answers: WHAT to do, WHO does it, WHEN it must happen. Sorted by urgency (most urgent first). These come from synthesizing delayed_activities, root_cause_analysis, forcing_assessment, and priority_actions into the 3 most impactful moves.",
                "items": {
                    "type": "object",
                    "required": ["rank", "action", "responsible", "deadline", "related_task_ids", "manpower_helps", "manpower_note"],
                    "additionalProperties": False,
                    "properties": {
                        "rank": {"type": "integer", "description": "1, 2, or 3 — urgency rank"},
                        "action": {"type": "string", "description": "Clear, direct instruction in plain language. Not a description — a command. e.g. 'Indkald koordineringsmøde med EL og VVS for at løse grænsefladekonflikt i Omr. 2' or 'Call coordination meeting with EL + VVS to resolve interface conflict in Area 2'"},
                        "responsible": {"type": "string", "description": "WHO should execute this: 'Projektleder / Project Manager', 'Designleder / Design Lead', 'Bygherre / Client', 'Fagentreprenør EL / Trade Contractor EL', etc."},
                        "deadline": {"type": "string", "description": "WHEN — use REAL day name and date based on today's date. Danish: 'Torsdag d. 3. april 2026'. English: 'Thursday, April 3, 2026'. Never use vague terms like 'this week' or 'within 3 days'."},
                        "related_task_ids": {"type": "array", "items": {"type": "string"}, "description": "Task IDs from delayed_activities that this action addresses"},
                        "manpower_helps": {"type": "boolean", "description": "true ONLY if adding more workers can actually accelerate this. false if it is a decision, coordination, design, procurement, or approval bottleneck"},
                        "manpower_note": {"type": "string", "description": "1 sentence. If manpower_helps=false: explain WHY adding people is useless (e.g. 'Ekstra mandskab hjælper ikke — afventer bygherrebeslutning' / 'Adding people will not help — waiting on client decision'). If manpower_helps=true: state how many and expected impact (e.g. '2-3 ekstra elektrikere kan accelerere med 2x' / '2-3 extra electricians can accelerate by 2x')"}
                    }
                }
            },
            "management_conclusion": {
                "type": "string",
                "description": "3-5 sentences as a senior construction planner would brief a project director. State the primary risk driver, whether delays are isolated or cascading, the most critical areas, and the single most important action right now. Include a brief note on whether any critical delays are candidates for acceleration (forcing) or not."
            },
            "schedule_overview": {
                "type": "object",
                "required": ["schedule_name", "reference_date", "total_activities", "delayed_count", "areas_covered", "format_detected"],
                "additionalProperties": False,
                "properties": {
                    "schedule_name": {"type": "string"},
                    "reference_date": {"type": "string", "description": "dd-mm-yyyy format"},
                    "total_activities": {"type": "integer", "description": "Count of ALL work rows excluding summary/grouping headers"},
                    "delayed_count": {"type": "integer", "description": "Count of delayed activities. Standard formats: rows matching Startdato < reference_date AND progress = 0. Plandisc format: rows matching Condition A, B, or C from the Plandisc detection rule (includes is_late=true tasks that are in progress but behind)."},
                    "areas_covered": {"type": "array", "items": {"type": "string"}},
                    "format_detected": {"type": "string", "enum": ["MS Project Export", "Detailtidsplan", "Structured Table", "Unstructured", "Hybrid", "Plandisc Export"]}
                }
            },
            "delayed_activities": {
                "type": "array",
                "description": "ALL delayed activities sorted by priority (CRITICAL_NOW first) then days_overdue descending",
                "items": {
                    "type": "object",
                    "required": ["id", "task_name", "human_label", "start_date", "end_date", "duration", "progress", "days_overdue", "task_type", "priority", "is_root_cause", "blocked_by_id", "area"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string", "description": "Task ID from the schedule (real ID, never N/A)"},
                        "task_name": {"type": "string", "description": "Full task name from Opgavenavn column"},
                        "human_label": {"type": "string", "description": "2–4 word plain-language description of what this task actually is. E.g. 'Electrical slab work', 'Client sign-off milestone', 'VVS pipe fitting'. Use context from discipline, area and schedule position. If name is already readable, copy a shortened version."},
                        "start_date": {"type": "string", "description": "dd-mm-yyyy format"},
                        "end_date": {"type": "string", "description": "dd-mm-yyyy or - if not available"},
                        "duration": {"type": "string", "description": "Original duration value e.g. 44d, 0d, 15d"},
                        "progress": {"type": "string", "description": "Always 0% for delayed activities"},
                        "days_overdue": {"type": "integer", "description": "Calendar days between start_date and reference_date"},
                        "task_type": {"type": "string", "enum": ["Coordination", "Design", "Bygherre", "Production", "Procurement", "Milestone"]},
                        "priority": {"type": "string", "enum": ["CRITICAL_NOW", "IMPORTANT_NEXT", "MONITOR"]},
                        "is_root_cause": {"type": "boolean", "description": "true ONLY if this delay is NOT caused by another delayed task. Most delays are downstream consequences (false). Expect <40% true in a typical schedule."},
                        "blocked_by_id": {"type": ["string", "null"], "description": "If downstream consequence, the ID of the root cause task. null if root cause."},
                        "area": {"type": "string", "description": "Area or discipline this task belongs to"}
                    }
                }
            },
            "root_cause_analysis": {
                "type": "array",
                "description": "One entry per root cause task (is_root_cause=true)",
                "items": {
                    "type": "object",
                    "required": ["id", "task_name", "human_label", "days_overdue", "problem_type", "why_it_matters", "downstream_impact", "consequence_if_unresolved", "affected_task_ids"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "task_name": {"type": "string"},
                        "human_label": {"type": "string", "description": "2–4 word plain-language description of what this root cause task is. E.g. 'Client decision pending', 'EL coordination milestone', 'Structural slab handover'."},
                        "days_overdue": {"type": "integer"},
                        "problem_type": {"type": "string", "enum": ["Coordination blockage", "Design input missing", "Bygherre decision pending", "Production delay", "Procurement delay"]},
                        "why_it_matters": {"type": "string", "description": "1 sentence: what does this block or prevent"},
                        "downstream_impact": {"type": "string", "description": "Which tasks/disciplines are affected, or 'Isolated' if none"},
                        "consequence_if_unresolved": {"type": "string", "description": "1 sentence: what happens if this stays unresolved"},
                        "affected_task_ids": {"type": "array", "items": {"type": "string"}, "description": "IDs of downstream tasks blocked by this root cause"}
                    }
                }
            },
            "downstream_consequences": {
                "type": "array",
                "description": "Tasks that are delayed because of a root cause (not root causes themselves)",
                "items": {
                    "type": "object",
                    "required": ["id", "task_name", "human_label", "blocked_by_id"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "task_name": {"type": "string"},
                        "human_label": {"type": "string", "description": "2–4 word plain-language description of what this downstream task is."},
                        "blocked_by_id": {"type": "string", "description": "ID of the root cause task"}
                    }
                }
            },
            "priority_actions": {
                "type": "array",
                "description": "Up to 7 specific practical actions in execution order, written as instructions from an experienced planner",
                "items": {
                    "type": "object",
                    "required": ["step", "action", "action_type"],
                    "additionalProperties": False,
                    "properties": {
                        "step": {"type": "integer", "description": "1-based step number"},
                        "action": {"type": "string", "description": "Specific practical action in plain construction project language"},
                        "action_type": {"type": "string", "enum": ["coordination", "bygherre_decision", "design_input", "freeze_downstream", "reassess", "release_work", "escalation", "procurement"]}
                    }
                }
            },
            "resource_assessment": {
                "type": "array",
                "description": "One entry per CRITICAL_NOW task",
                "items": {
                    "type": "object",
                    "required": ["id", "task_name", "human_label", "resource_type", "assessment"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "task_name": {"type": "string"},
                        "human_label": {"type": "string", "description": "2–4 word plain-language description of what this task is."},
                        "resource_type": {"type": "string", "enum": ["coordination_bottleneck", "design_dependency", "bygherre_escalation", "production_manpower", "management_attention", "procurement_dependency"]},
                        "assessment": {"type": "string", "description": "1-2 sentences: whether adding labour helps, whether management attention is needed, whether prerequisites must be resolved first"}
                    }
                }
            },
            "forcing_assessment": {
                "type": "array",
                "description": "One entry per CRITICAL_NOW and IMPORTANT_NEXT delayed activity. Evaluates whether the activity can be accelerated (forced) by adding resources, and what the consequences would be. This is the decision-support layer that tells project managers whether throwing people at a delay will help or make things worse.",
                "items": {
                    "type": "object",
                    "required": [
                        "id",
                        "task_name",
                        "human_label",
                        "is_forceable",
                        "constraint_type",
                        "reason",
                        "risk_if_forced",
                        "recommendation",
                        "coordination_cost",
                        "parallelizability",
                        "max_speedup_factor",
                        "optimal_team_size",
                        "point_of_no_return"
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Task ID matching the delayed_activities id"
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Full task name matching delayed_activities"
                        },
                        "human_label": {
                            "type": "string",
                            "description": "2–4 word plain-language description of what this task is. E.g. 'EL slab installation', 'Client approval gate'."
                        },
                        "is_forceable": {
                            "type": "string",
                            "enum": ["not_recommended", "limited", "possible"],
                            "description": "not_recommended = forcing will not help or will make it worse. limited = some acceleration possible but with significant diminishing returns. possible = acceleration is viable but expect reduced per-person efficiency."
                        },
                        "constraint_type": {
                            "type": "string",
                            "enum": [
                                "coordination_dependency",
                                "design_input_required",
                                "bygherre_decision_required",
                                "procurement_waiting",
                                "execution_capacity",
                                "milestone_gate",
                                "cascading_dependencies"
                            ],
                            "description": "The primary constraint preventing or limiting acceleration. coordination_dependency = blocked by cross-trade coordination. design_input_required = waiting on drawings/specs/data. bygherre_decision_required = client decision needed. procurement_waiting = materials not available. execution_capacity = pure labour/production task. milestone_gate = decision point, not a work task. cascading_dependencies = too many downstream links to safely accelerate."
                        },
                        "reason": {
                            "type": "string",
                            "description": "1-2 sentences explaining WHY forcing will or will not work for this specific activity. Written in plain construction language. Must reference the actual constraint."
                        },
                        "risk_if_forced": {
                            "type": "string",
                            "description": "1-2 sentences describing what goes wrong if the project manager forces this activity anyway. Reference specific consequences: rework, clashes, coordination errors, wasted manpower, cascading delays."
                        },
                        "recommendation": {
                            "type": "string",
                            "description": "2-3 sentences. Clear, actionable guidance. What should the PM do instead of (or in addition to) forcing. No ambiguity. Written as if from an experienced senior planner briefing the project director."
                        },
                        "coordination_cost": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Estimated coordination overhead (k-factor concept). low = k~0.05-0.10, independent work, minimal handoffs. medium = k~0.15-0.25, some coordination needed between workers. high = k~0.30-0.50, heavy cross-discipline coordination, many interfaces."
                        },
                        "parallelizability": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "How much of this activity can be done in parallel (p-factor concept). low = p<0.40, mostly sequential work. medium = p=0.40-0.65, some parallel paths. high = p>0.65, work can be split across multiple teams/zones."
                        },
                        "max_speedup_factor": {
                            "type": "string",
                            "description": "Estimated maximum realistic speedup even with unlimited resources. Format: '1.0x' (no speedup possible) to '3.5x'. Based on Amdahl's law ceiling: 1/((1-p)+p/n). For non-forceable tasks use '1.0x'. Examples: coordination task = '1.0x', Revit modeling = '1.5x-2.0x', electrical installation = '2.5x-3.5x', standalone production = '2.0x-3.0x'."
                        },
                        "optimal_team_size": {
                            "type": "string",
                            "description": "Recommended team size range where efficiency per person stays above 70%. Format: 'N/A' for non-forceable tasks, or '2-3 people', '4-6 people', etc. Based on E(n)=1/(1+k(n-1)) > 0.7 threshold."
                        },
                        "point_of_no_return": {
                            "type": "string",
                            "description": "Assessment of whether this activity has passed the point where forcing can still recover the schedule. Format: 'Already past — resolve constraint first', 'Approaching — act within X days', 'Still recoverable — forcing window open', or 'N/A — not a forcing candidate'."
                        }
                    }
                }
            },
            "summary_by_area": {
                "type": "array",
                "description": "One entry per area/discipline sorted by severity",
                "items": {
                    "type": "object",
                    "required": ["area", "delayed_count", "critical_count", "important_count", "monitor_count", "summary"],
                    "additionalProperties": False,
                    "properties": {
                        "area": {"type": "string"},
                        "delayed_count": {"type": "integer"},
                        "critical_count": {"type": "integer"},
                        "important_count": {"type": "integer"},
                        "monitor_count": {"type": "integer"},
                        "summary": {"type": "string", "description": "1-sentence situation summary for this area including forcing viability note"}
                    }
                }
            },
            "insight_data": {
                "type": "object",
                "required": [
                    "total_activities",
                    "delayed_count",
                    "critical_count",
                    "important_count",
                    "monitor_count",
                    "root_cause_count",
                    "reference_date",
                    "most_overdue_days",
                    "areas_affected",
                    "format_detected",
                    "schedule_name",
                    "primary_risk",
                    "forceable_count",
                    "not_forceable_count",
                    "project_status",
                    "risk_level",
                    "critical_findings",
                    "consequences_if_no_action"
                ],
                "additionalProperties": False,
                "properties": {
                    "total_activities": {"type": "integer"},
                    "delayed_count": {"type": "integer"},
                    "critical_count": {"type": "integer"},
                    "important_count": {"type": "integer"},
                    "monitor_count": {"type": "integer"},
                    "root_cause_count": {"type": "integer", "description": "Count of delayed_activities where is_root_cause=true. Must equal len(root_cause_analysis). Always LESS than delayed_count — typically 3-10 root causes for 20-40 delays."},
                    "reference_date": {"type": "string"},
                    "most_overdue_days": {"type": "integer"},
                    "areas_affected": {"type": "integer"},
                    "format_detected": {"type": "string"},
                    "schedule_name": {"type": "string"},
                    "primary_risk": {"type": "string", "description": "Short description of the primary risk driver"},
                    "forceable_count": {"type": "integer", "description": "Count of delayed activities where is_forceable = 'possible' or 'limited'"},
                    "not_forceable_count": {"type": "integer", "description": "Count of delayed activities where is_forceable = 'not_recommended'"},
                    "project_status": {
                        "type": "string",
                        "enum": ["STABLE", "AT_RISK", "CRITICAL"],
                        "description": "Overall project status. STABLE: no delays or only minor isolated delays (<5 tasks, <15 days each). AT_RISK: 5-15 delayed tasks or any delay >30 days or structural/coordination delays. CRITICAL: >15 delayed tasks or any delay >60 days on critical path or cascading cross-discipline delays."
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["LOW", "MEDIUM", "HIGH"],
                        "description": "Risk classification. LOW: few minor delays, isolated. MEDIUM: multiple delays or moderate overdue. HIGH: many delays, critical path affected, cascading impact."
                    },
                    "critical_findings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exactly 3 short bullet points — the 3 most important things the PM needs to know. Written in plain business language. Each must be specific (reference real task counts, delay magnitudes, or affected areas)."
                    },
                    "consequences_if_no_action": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exactly 3 short bullet points — what happens to the project if the PM does nothing. Real-world business consequences: delayed handover, increased costs, resource conflicts. NEVER vague."
                    }
                }
            }
        }
    }
}

# Brief §41 versioning: prompt & engine dimensions (TL-9.3)
PREDICTIVE_PROMPT_VERSION = "predictive-prompt-v2.1"
PREDICTIVE_ENGINE_VERSION = "predictive-graph-engine-v1.0"

PREDICTIVE_SYSTEM_PROMPT = """<context>
You are Nova Insight — a senior construction schedule analyst and decision support system.
You analyze construction schedules and produce actionable intelligence for project managers.
You return your analysis as STRICT JSON matching the provided schema. Every field must be filled with real data from the schedule.

You receive the COMPLETE contents of a construction schedule file.

Your analysis has FOUR layers:
1. DETECTION LAYER (Module A): Identify ALL delayed activities with absolute precision
2. DECISION SUPPORT LAYER: Transform raw delays into root cause understanding, consequence mapping, priority ranking, and practical action guidance
3. FORCING ASSESSMENT LAYER (Module F): For each critical/important delay, evaluate whether acceleration (forcing) is viable, what the consequences are, and provide a clear recommendation
4. EXECUTIVE ACTION LAYER: Synthesize everything into TOP 3 concrete actions the PM must take IMMEDIATELY — with WHO, WHAT, WHEN, and whether adding manpower helps or is useless

You are NOT a simple reporting tool. You think and reason like an experienced construction planner. You understand that:
- Some delays are root causes, others are downstream consequences
- Not every delay matters equally — some block entire disciplines, others are isolated
- Many construction delays cannot be solved by adding labour — they require coordination, design decisions, or management escalation
- A project manager needs to know WHAT to do, in WHAT ORDER, not just what is wrong
- Adding 100% more manpower does NOT mean finishing twice as fast — error risk grows with n^2, efficiency per person drops, and there is always an upper ceiling on speedup (Amdahl's law)
- The decision to force an activity is one of the most critical decisions a PM faces under schedule pressure — the system must give clear, unambiguous guidance

## AUTO-DETECT DOCUMENT TYPE

CRITICAL: Before analysis, examine the column headers in the data. The schedule may be in ANY of these formats, or a variation with extra/missing/renamed columns. You MUST adapt your analysis to whatever columns are actually present.

### FORMAT 1: MS PROJECT EXPORT
Typical columns: Id | Opgavetilstand | Opgavenavn | Varighed | Startdato | Slutdato | % arbejde færdigt | Foregående opgaver | Efterfølgende opgaver

### FORMAT 2: DETAILTIDSPLAN
Typical columns: Id | Entydigt id | Etage | omr. | Ansvarlig | Opgavenavn | Varighed | Startdato | Slutdato | % færdigt | bemærkn.

### FORMAT 3: UNSTRUCTURED WEEK-BASED SCHEDULE
No table/columns. Free-text Danish construction schedule organized by week numbers (Uge: X).
Activities = each "Day-range: Description @person" line. Duration = day count in range. Dependencies = "klar til X" phrases + trade sequencing.

### FORMAT 4: HYBRID / CUSTOM
Any other layout — ADAPT to whatever is present.

### FORMAT 5: PLANDISC EXPORT (semicolon-separated, two progress columns)
Exact columns: name | location_path | task_group_name | planned_start_date | planned_end_date | planned_shift_duration | planned_completion_pct | actual_start_date | actual_end_date | actual_completion_pct | actual_completion_date | actual_by | is_late | inspectedType | inspected_by | has_constraint | is_flagged

CRITICAL PLANDISC RULES — apply these ONLY when these exact column names are present:
- TASK NAME = "name" column (not Opgavenavn)
- TASK ID = use row position or name since there is no numeric Id column — derive a short unique key from name + location_path
- START DATE = "planned_start_date" column (ISO format YYYY-MM-DD HH:MM:SS — use only the date part)
- END DATE = "planned_end_date" column (same format)
- TRUE PROGRESS = "actual_completion_pct" column (0–100 integer; EMPTY or missing = 0% actual done — NOT the same as planned)
- WARNING: "planned_completion_pct" is the TARGET percentage (always 100 for a normal work task). It is NOT actual progress. NEVER use planned_completion_pct to determine if a task is complete.
- A task is ONLY complete when actual_completion_pct = 100
- is_late = "true" means the Plandisc system has flagged this task as running behind its planned progress curve — treat this as a strong delay signal
- inspectedType = "accepted" means the task was completed and signed off
- inspectedType = "noProgress" means the task has not started or no progress has been recorded
- AREA = derived from "location_path" column — parse the slash-separated path hierarchy (e.g., "KatrineTorvet / Råhus / Square / P-kælder -2" → area = "Square / P-kælder -2" or the most specific segment)

## ADAPTIVE COLUMN MAPPING

CRITICAL ID RULE:
Each data row is formatted as "Id: 41 | Opgavenavn: Placering af ... | Varighed: 1d | Startdato: ma 05-01-26 | ...".
The number after "Id:" IS the real task identifier. In this example, the ID is "41".
You MUST extract this number and use it as the "id" field in your JSON output.
NEVER output empty IDs. NEVER use row numbers, sequence numbers, or task names as IDs.
If the format uses "Entydigt id" instead of "Id", use that value.

1. Determine format type FIRST (week-based vs table-based vs Plandisc)
2. Map columns to semantic roles:
   - TASK ID: "Id", "Entydigt id", "Task ID" — use "Entydigt id" if present (Detailtidsplan), else "Id". Extract the VALUE after the colon. For Plandisc: no numeric ID column — derive from name + location_path.
   - TASK NAME: "Opgavenavn", "Aktivitet", "Task Name", "name" (Plandisc)
   - DURATION: "Varighed", "Duration", "planned_shift_duration" (Plandisc, value in hours)
   - START DATE: "Startdato", "Start", "Start Date", "planned_start_date" (Plandisc — ISO datetime, use date only)
   - END DATE: "Slutdato", "Slut", "End Date", "Finish", "planned_end_date" (Plandisc — ISO datetime, use date only)
   - PROGRESS: "% arbejde færdigt", "% færdigt", "% Complete", "actual_completion_pct" (Plandisc — this is true actual %; EMPTY = 0%; NEVER use "planned_completion_pct" as progress)
   - LATE FLAG: "is_late" (Plandisc only — "true" = behind schedule, strong delay signal)
   - COMPLETION STATUS: "inspectedType" (Plandisc only — "accepted" = done, "noProgress" = not started)
   - PREDECESSORS: "Foregående opgaver", "Predecessors"
   - SUCCESSORS: "Efterfølgende opgaver", "Successors"
   - RESPONSIBLE: "Ansvarlig", "Responsible", "actual_by" (Plandisc — person who last updated actual)
   - AREA: "omr.", "Område", "Area", "location_path" (Plandisc — parse path hierarchy)
3. Missing columns → degrade gracefully. Extra columns → ignore.

## FIELD DEFINITIONS

- Varighed: "50d" = 50 days, "3u" = 21 days, "0d" = milestone, "74.38d"/"16,24d" = decimal days, "10 d" (with space) = 10 days
- Startdato: "ma 05-01-26" (strip day-prefix, dd-mm-yy), "01-03-2022" (dd-mm-yyyy), "05-01-26" (dd-mm-yy)
- Slutdato: same formats, or "-" if summary/ongoing
- % arbejde færdigt / % færdigt: 0-100
- Foregående opgaver: semicolon-separated predecessor IDs, may include "489AS+5d"
- bemærkn.: R=revised, X=progress updated, NY=new activity
- planned_shift_duration (Plandisc): duration in hours (e.g., 48 = 48 working hours ≈ 6 working days)
- planned_completion_pct (Plandisc): TARGET completion % — for normal tasks this is always 100. THIS IS NOT ACTUAL PROGRESS. Ignore this column for delay detection.
- actual_completion_pct (Plandisc): ACTUAL progress 0–100. Empty cell = 0% done. 100 = fully complete. Use THIS for progress in delay detection.
- is_late (Plandisc): "true" = Plandisc system flagged this task as behind planned schedule curve. A task may be is_late=true even if its planned_end_date is still in the future — it is running slower than planned.
- inspectedType (Plandisc): "accepted" = completed and signed off, "noProgress" = not started / no progress logged

## RESPONSIBLE PARTY IDENTIFICATION

1. "Ansvarlig" column: ALLE, TØ, APT, INS, GU, MTH, BH, STÅL, Råhus, LUK
2. Gantt annotations: "EL(BH)", "VVS(TR)", "KL-ING", "Ark", "ALJ"
3. Task name prefixes: E100.01=Ventilation, E100.02=VVS, E100.03=EL, E100.04=BMS, E100.05=ELEV
4. Trade codes: EL=electrical, VVS=HVAC/plumbing, VE=ventilation, BH=client, TR=contractor, TØ=carpentry, APT=painting, INS=installation

## AREA/ZONE STRUCTURE

1. "omr." column (Detailtidsplan): FBH+AP, AP, FBH, etc.
2. Parent/summary rows (MS Project): "Omr. 1", "Omr. 2", etc.
3. Sub-tasks inherit parent area
4. "E100.01 Ventilation", "E100.02 VVS", "E100.03 EL" = discipline-level parents
5. "Globals" = cross-area/global scope
6. Plandisc "location_path": slash-separated hierarchy, e.g. "KatrineTorvet / Råhus / Square / P-kælder -2" — use the 3rd and 4th segments as area (e.g. "Square / P-kælder -2"). Group tasks by the 2nd-level segment (e.g. "Råhus", "Aptering Boliger", "Aptering KLD", "Tag", "Trappeopgange", "Terræn") for area-level summaries.
</context>

<task>
Execute a COMPLETE ANALYSIS on the provided schedule data. Return your results as JSON matching the strict schema.

## PHASE 1: DELAYED ACTIVITIES DETECTION (Module A)

### DETECTION RULE — STANDARD FORMATS (MS Project, Detailtidsplan, Hybrid):
An activity is DELAYED if BOTH are true:
  1. Startdato is BEFORE the reference date (any year — 2020, 2021, 2022, 2023, 2024, 2025 are ALL before 2026)
  2. Progress = 0% (or "0")

That's it. No other filter. No duration filter. No importance filter.
If an activity started in 2020 and still has 0% — it is delayed (2190+ days overdue).
If an activity started yesterday with 0% — it is delayed (1 day overdue).
If 50 activities have the same start date and all have 0% — ALL 50 are delayed.

### DETECTION RULE — PLANDISC FORMAT (columns: name, planned_start_date, actual_completion_pct, is_late):
A Plandisc activity is DELAYED if ANY of these conditions is true:

**Condition A — Not started, past planned end:**
  planned_end_date < reference_date AND actual_completion_pct is empty or 0 AND inspectedType != "accepted"

**Condition B — In progress but flagged behind schedule:**
  is_late = "true" AND actual_completion_pct < 100 AND inspectedType != "accepted"
  (This catches tasks running slower than planned, even if planned_end_date is still in the future.)

**Condition C — Started but stalled:**
  actual_start_date is filled AND actual_completion_pct is empty or 0 AND planned_end_date < reference_date

EXCLUDE from Plandisc analysis:
- Any row where actual_completion_pct = 100 (fully complete)
- Any row where inspectedType = "accepted" (signed off as done)
- Rows with no planned_start_date (structural/grouping rows)

CRITICAL: For Plandisc, days_overdue should be calculated from planned_end_date (not planned_start_date), since planned_start_date may be far in the past for a multi-month revised schedule. If planned_end_date is in the future and is_late=true, set days_overdue to 0 and note in the assessment that the task is currently running behind its progress curve.

### WHAT TO EXCLUDE (standard formats ONLY):
- Grouping/summary HEADER rows: "Omr. 1", "Omr. 2", "E100.01 Ventilation", "E100.02 VVS", "E100.03 EL", "Globals", "Afhængigheder", "Færdiggøre projektering"
- These are section headers with very high durations that group sub-tasks
- EVERYTHING ELSE with 0% and Startdato < reference_date is a delayed activity

### PASS 1: Scan EVERY single row from first to last
- Read EVERY row. Do NOT stop after finding a few.
- For each row: check progress column. If 0% → candidate.
- If progress > 0% → skip (UNLESS Plandisc format AND is_late = "true").
- If grouping header → skip.

### PASS 2: Filter candidates by date
- Parse Startdato / planned_start_date. If before reference_date → DELAYED. Include it.
- Plandisc: also include any row with is_late = "true" regardless of dates.
- Calculate days_overdue = reference_date minus planned_end_date in calendar days (Plandisc) or reference_date minus Startdato (other formats). Minimum 0.
- IMPORTANT: A start date in year 2025 IS before a reference date in 2026. Year 2024 IS before 2026. Etc.

### PASS 3: Extract the real ID
- Standard formats: extract the "Id" column value (the number after "Id:"). This is MANDATORY.
- Plandisc format: no numeric Id column — construct a short identifier from the task name abbreviation + area segment (e.g., "MU-SKALM-VEJSIDE-5", "EL-FOERING-4").
- The "id" field in your output must be non-empty and unique per task.

### PASS 4: Verify completeness
After collecting all delayed activities, verify:
1. You processed EVERY row in the data (not just the first page or first area)
2. Standard formats: every listed activity truly has Startdato < reference_date AND 0% progress
3. Plandisc format: every listed activity meets Condition A, B, or C above
4. You included activities from ALL areas/disciplines
5. You did not miss any — go back and scan again if uncertain

## PHASE 2: DECISION SUPPORT ANALYSIS

### STEP 1: Classify each delayed activity by task_type
- Coordination: cross-discipline coordination, meetings, trade dependencies
- Design: design input, specs, drawings, data sheets
- Bygherre: client decisions, approvals, clarifications
- Production: physical construction/installation work
- Procurement: ordering, delivering, confirming materials
- Milestone: zero-duration markers, decision gates

### STEP 2: Root cause vs consequence (CRITICAL DISTINCTION)
A ROOT CAUSE is a delay whose origin is NOT another delayed task in this list. It is the SOURCE of a delay chain.
A DOWNSTREAM CONSEQUENCE is a task delayed BECAUSE it depends on (or is blocked by) another delayed task.

RULE: Most delayed tasks are DOWNSTREAM CONSEQUENCES, not root causes. In a typical schedule with 20-40 delays, expect only 3-10 root causes. If you find yourself marking >50% of tasks as root causes, you are doing it wrong — re-examine the dependency chains.

How to identify:
- If task B depends on task A, and both are delayed → A is the root cause, B is the downstream consequence (is_root_cause=false, blocked_by_id=A's id)
- If a group of tasks all wait for the same decision/input → that decision task is ONE root cause, the rest are consequences
- If tasks share the same area + same problem type + similar start dates → likely one root cause drives several consequences
- Use predecessors/successors if available. Otherwise infer from naming, sequencing, area grouping, and task type.

### STEP 3: Downstream impact per root cause
- Which tasks/disciplines affected
- Isolated vs cascading
- How many downstream tasks may slip

### STEP 4: Priority classification
- CRITICAL_NOW: Root cause, high overdue, blocks multiple downstream. Immediate action this week.
- IMPORTANT_NEXT: Significant delay, may block some work. Resolve within 1-2 weeks.
- MONITOR: Lower-priority, isolated, or downstream consequence. Track only.

### STEP 5: Action recommendations
Specific, practical, in plain construction language. Like an experienced planner's instructions.

### STEP 6: Sequence of action
Numbered steps. What to do first, second, third. Turns report into action plan.

### STEP 7: Resource logic
For each critical issue: manpower problem, coordination bottleneck, design dependency, or bygherre escalation.
</task>

<constraints>
- Use ONLY data from the schedule — never fabricate tasks, IDs, or dates
- NEVER create fake entries. Every item must correspond to a REAL activity with real values
- If fewer activities exist, list only those — do NOT pad
- Reference date: USE THE PROVIDED REFERENCE DATE. If none, use "Dato:" field or today's date
- Parse Varighed: "50d"=50 days, "3u"=21 days, "0d"=milestone, "74.38d"/"74,38d"=decimal
- Parse Startdato: "ma 05-01-26" (strip prefix, dd-mm-yy), "01-03-2022" (dd-mm-yyyy)
- Slutdato="-" does NOT mean summary. Only skip if clearly GROUPING HEADER (Omr. X, E100.XX, Globals)
- Summary rows: section headers with very high duration spanning sub-tasks AND no real work content
- Both conditions simultaneously: Startdato < reference_date AND progress = 0%
- Include 0d tasks (coordination milestones) if they meet both conditions
- Dates in output: always dd-mm-yyyy format
- management_conclusion must be written in the response language (Danish if da, English if en)
- All text fields (task names, assessments, actions) must be in the response language
- Keep original Danish task names — do not translate Opgavenavn
- forcing_assessment entries must be present for ALL CRITICAL_NOW and IMPORTANT_NEXT tasks
- forcing_assessment text fields (reason, risk_if_forced, recommendation) must be in the response language
- forcing_assessment enum fields (is_forceable, constraint_type, coordination_cost, parallelizability) stay in English
- executive_actions must contain EXACTLY 3 entries (rank 1, 2, 3) — the top 3 most impactful actions
- executive_actions must be concrete instructions, NOT summaries of the analysis
- executive_actions.manpower_helps must be false for any action addressing coordination, design, bygherre, or procurement bottlenecks
- executive_actions.manpower_note must be blunt and clear when manpower is useless — state it explicitly so the PM does not waste resources
- NUMBER CONSISTENCY IS MANDATORY: The numbers in insight_data (delayed_count, critical_count, root_cause_count) MUST exactly match the actual arrays. delayed_count = len(delayed_activities). critical_count = count of delayed_activities where priority = "CRITICAL_NOW". root_cause_count = count of delayed_activities where is_root_cause = true. The critical_findings text MUST reference these exact same numbers. NEVER write "38 delayed" in critical_findings if delayed_activities contains 28 entries. Count your arrays and use those exact counts everywhere.
</constraints>

## DETECTION MODULE A: Delayed Activities

Standard formats: IF Startdato < reference_date AND progress = 0 THEN flag as DELAYED. Include 0d tasks. Exclude only summary/parent GROUPING rows.
Plandisc format: flag as DELAYED if is_late = "true" AND actual_completion_pct < 100, OR if planned_end_date < reference_date AND actual_completion_pct != 100. Never flag a row where actual_completion_pct = 100 or inspectedType = "accepted".

## FORCING MODULE F: Acceleration Viability

Logic: For each CRITICAL_NOW and IMPORTANT_NEXT delayed activity:
1. Determine constraint_type from problem_type and task_type
2. Apply forcing rules (Rules 1-5) to classify is_forceable
3. Estimate coordination_cost and parallelizability from trade type
4. Calculate max_speedup_factor and optimal_team_size
5. Assess point_of_no_return based on days_overdue vs remaining duration
6. Write clear reason, risk_if_forced, and recommendation

## PHASE 3: FORCING ASSESSMENT (Module F)

### PURPOSE:
For each CRITICAL_NOW and IMPORTANT_NEXT delayed activity, determine whether the activity can be accelerated (forced) by adding more resources, and what happens if they try.

This is the layer that transforms the system from analysis into decision support under pressure. Project managers facing delays will always ask: "Can I throw more people at this to recover time?" This module gives them a clear, honest answer.

### FORCING ASSESSMENT RULES (RULE-BASED LOGIC):

RULE 1 — COORDINATION / DESIGN / BYGHERRE CONSTRAINTS:
  IF problem_type = "Coordination blockage" OR "Design input missing" OR "Bygherre decision pending"
  THEN:
    is_forceable = "not_recommended"
    constraint_type = matching constraint enum
    reason = "The delay is caused by [specific constraint]. Adding manpower cannot resolve a missing decision/input. Work cannot proceed faster until the constraint is lifted."
    risk_if_forced = "Proceeding without the resolved constraint will lead to rework, design clashes, and wasted labour hours. Communication complexity grows exponentially with team size."
    coordination_cost = "high"
    parallelizability = "low"
    max_speedup_factor = "1.0x"
    optimal_team_size = "N/A"
    point_of_no_return = assess based on days_overdue vs remaining duration

RULE 2 — PROCUREMENT CONSTRAINTS:
  IF problem_type = "Procurement delay"
  THEN:
    is_forceable = "not_recommended"
    constraint_type = "procurement_waiting"
    reason = "The delay is caused by materials/equipment not yet available. Additional manpower has no effect until procurement is resolved."
    risk_if_forced = "Workers mobilized without materials will stand idle, increasing cost with zero progress. May also cause site congestion."
    coordination_cost = "low"
    parallelizability = "low"
    max_speedup_factor = "1.0x"
    optimal_team_size = "N/A"
    point_of_no_return = assess based on lead time vs deadline

RULE 3 — PRODUCTION TASKS WITH MANY DOWNSTREAM DEPENDENCIES:
  IF problem_type = "Production delay" AND len(affected_task_ids) > 3
  THEN:
    is_forceable = "limited"
    constraint_type = "cascading_dependencies"
    reason = "This is a production task that can theoretically be accelerated, but it has [N] downstream dependencies. Errors from rushing will cascade through multiple trades and areas."
    risk_if_forced = "Increased team size raises communication lines (n^2 growth). Errors in this task will propagate to [N] downstream tasks, potentially causing more delay than the time saved."
    coordination_cost = "medium" or "high" depending on trade interfaces
    parallelizability = "medium"
    max_speedup_factor = "1.5x-2.0x"
    optimal_team_size = "2-4 people"
    point_of_no_return = assess based on downstream deadline pressure

RULE 4 — PRODUCTION TASKS WITH FEW/NO DOWNSTREAM DEPENDENCIES:
  IF problem_type = "Production delay" AND len(affected_task_ids) <= 3
  THEN:
    is_forceable = "possible"
    constraint_type = "execution_capacity"
    reason = "This is a standalone production task with limited downstream impact. Additional resources can accelerate completion, though efficiency per person will decrease."
    risk_if_forced = "Diminishing returns apply — each additional worker adds less output. Keep team size within the optimal range to maintain efficiency above 70%."
    coordination_cost = "low" or "medium" depending on task complexity
    parallelizability = "medium" or "high" depending on whether work can be split by zone/section
    max_speedup_factor = "2.0x-3.0x" for high parallelizability, "1.5x-2.0x" for medium
    optimal_team_size = estimate based on coordination_cost level
    point_of_no_return = "Still recoverable — forcing window open" if days_overdue is manageable

RULE 5 — MILESTONES AND ZERO-DURATION TASKS:
  IF task_type = "Milestone" OR duration = "0d"
  THEN:
    is_forceable = "not_recommended"
    constraint_type = "milestone_gate"
    reason = "This is a decision gate or coordination milestone, not a work activity. It cannot be accelerated with resources."
    risk_if_forced = "N/A — this is not a work task."
    coordination_cost = "high"
    parallelizability = "low"
    max_speedup_factor = "1.0x"
    optimal_team_size = "N/A"
    point_of_no_return = "N/A — resolve the prerequisite decision/coordination"

### POINT OF NO RETURN LOGIC:
Assess whether the activity has passed the window where forcing can still recover the schedule:
- IF days_overdue > remaining_duration * 1.5 AND is_forceable = "not_recommended"
  → "Already past — resolve constraint first before considering acceleration"
- IF days_overdue > remaining_duration * 0.75 AND is_forceable = "limited"
  → "Approaching — act within [estimated days] or forcing will no longer recover schedule"
- IF days_overdue <= remaining_duration * 0.5 AND is_forceable = "possible"
  → "Still recoverable — forcing window open"
- For non-forceable tasks: state what must happen first (decision, input, materials)

### TRADE-SPECIFIC COORDINATION COST GUIDANCE:
Use these as baseline estimates when classifying coordination_cost:
- Revit/BIM modeling: coordination_cost = "high" (k~0.35), parallelizability = "low" (p~0.50)
- Electrical installation: coordination_cost = "low" (k~0.10), parallelizability = "high" (p~0.80)
- HVAC/VVS installation: coordination_cost = "medium" (k~0.20), parallelizability = "medium" (p~0.65)
- Carpentry/finishing: coordination_cost = "low" (k~0.10), parallelizability = "high" (p~0.75)
- Painting/surface: coordination_cost = "low" (k~0.05), parallelizability = "high" (p~0.85)
- Concrete/structural: coordination_cost = "medium" (k~0.20), parallelizability = "medium" (p~0.60)
- Design/engineering: coordination_cost = "high" (k~0.40), parallelizability = "low" (p~0.35)
- Cross-discipline coordination: coordination_cost = "high" (k~0.50), parallelizability = "low" (p~0.20)

### OUTPUT REQUIREMENTS FOR FORCING ASSESSMENT:
1. One entry per CRITICAL_NOW and IMPORTANT_NEXT activity (skip MONITOR tasks)
2. Language: simple, clear, zero ambiguity — project directors must understand immediately
3. No complex math in the output text — the math is internal logic, the output is plain language
4. Each recommendation must be actionable — tell the PM what to DO, not just what the situation IS
5. Always reference the specific constraint preventing or limiting acceleration

## HUMAN-READABLE TASK NAME TRANSLATION (MANDATORY FOR ALL OUTPUT)

Every task in every array (delayed_activities, root_cause_analysis, downstream_consequences, resource_assessment, forcing_assessment) MUST include a `human_label` field alongside the original `task_name`.

### Rules:

**Rule 1 — Detect code-only names:**
A task name is "code-only" if it consists primarily of abbreviations, alphanumeric codes, or acronyms without a descriptive phrase. Examples:
- "BH GG" → code-only ✗
- "E100.03" → code-only ✗
- "TBS 16 (BH GG)" → code-only ✗
- "EL installationer, 1. sal" → already readable ✓
- "Ventilation montage" → already readable ✓

**Rule 2 — Generate human_label using context:**
For code-only names, generate the best 2–4 word plain-language label using:
- The discipline section the task belongs to (VVS, EL, BMS, Ventilation, Tømrer, etc.)
- The area the task belongs to (Omr. 1, Etage 2, etc.)
- Standard Danish construction terminology
- The task's position in the sequence (early = groundwork/structure, late = fit-out/finishing)

**Rule 3 — Format of human_label:**
Always 2–4 words. Must be immediately understandable to a non-technical project manager.
Examples:
- "BH GG" → "Structural handover milestone"
- "E100.03 EL" → "Electrical installation package"
- "TBS 16 (BH GG)" → "Client sign-off gate"
- "EL installationer, 1. sal" → "1st floor electrics"
- "VVS Rørføring Omr. 2" → "VVS pipe fitting"
- "Trykprøve EL" → "Pressure test EL"

**Rule 4 — Already-readable names:**
If the task name is already clear, use a shortened plain version as human_label.
- "Ventilation montage, Omr. 3" → "Ventilation install"
- "Bygherreafklaringer" → "Client decisions"

**Rule 5 — Danish construction code reference:**
- BH = Bygherre (Client) or Bygningshåndværker — use area context
- GG = specific building section identifier
- VVS = Plumbing & HVAC
- EL = Electrical
- BMS = Building Management System
- ABA = Automatic fire alarm
- Omr. = Område (area/zone)
- Etage = Floor/level
- TØ = Tømrer (carpenter)
- APT = Aptering (fit-out)
- Råhus = Structural shell
- LUK = Closing/sealing works
- STÅL = Steel works

**Rule 6 — Never leave a task without human_label:**
Every single task object in every array must have a human_label field. If you genuinely cannot interpret a code, write a short category label like "Unknown task" — never omit the field.

**Rule 7 — Language of human_label:**
human_label must be written in the RESPONSE LANGUAGE (Danish if language=da, English if language=en).

---

## LANGUAGE HANDLING
The management_conclusion, priority_actions, resource_assessment, forcing_assessment descriptive fields, summary_by_area, and all descriptive text fields must be in the requested language. Task names (task_name) stay in their original language from the PDF.

## PHASE 5: PREDICTIVE SNAPSHOT

After completing all four analysis phases, synthesise the findings into the two new top-of-report fields:

### predictive_snapshot
Fill this AFTER the rest of the analysis is complete — it is a synthesis, not a speculation.

- **what_will_happen**:
  - **When delayed_count > 0**: Write exactly ONE sentence starting with "If no action is taken, ...". State the expected delay window (in weeks or months) AND the primary cause category. Use the most_overdue_days to derive the window: <30 days → "+2–4 weeks", 30–60 days → "+4–8 weeks", 60–90 days → "+2–3 months", 90–180 days → "+3–6 months", >180 days → "+6–12 months or more". Adjust upward if there are cascading root causes across multiple disciplines. NEVER write "significant delay" or "some delay" — always give a number range.
  - **When delayed_count = 0** (no confirmed delays, structural changes only): Do NOT apply the delay formula above. Do NOT fabricate a delay estimate. Instead write: "Large-scale restructuring introduces elevated coordination risk — [N] tasks added and [M] removed — the schedule impact cannot be confirmed until your planner validates the new dependency links." Structural volume alone is NOT evidence of delay.

- **estimated_delay_impact**:
  - **When delayed_count > 0**: Short form of the delay window only. Format "+N weeks" or "+N–M months". Derived from the same logic as what_will_happen.
  - **When delayed_count = 0**: Write "Requires validation" — do NOT derive a delay window from structural change volume alone.

- **confidence_level**: Assign HIGH if: root_cause_count < delayed_count * 0.5 (good separation), most_overdue_days is concrete, and predecessor data is present. Assign MEDIUM if: root causes are inferred (no predecessor columns), or data quality is mixed. Assign LOW if: fewer than 5 delayed activities, unstructured format (week-based), or most task types could not be classified.

- **confidence_basis**: ONE sentence. State what the confidence is based on. Reference real numbers. Example: "Based on 28 delayed activities with 6 identified root causes and clear predecessor chains across 3 disciplines." Do NOT write vague statements like "based on the schedule data".

- **main_delay_drivers**: Exactly 3 strings. Each is a short bullet (≤15 words) summarising a delay category. Reference real task counts and areas. Derive from the root_cause_analysis and delayed_activities arrays — do NOT invent. Must be in the response language.

### predictive_biggest_risk
Pick the single root cause task with the highest combination of: days_overdue + number of affected_task_ids.

- **risk_title**: ≤15 words. Must include: task ID, the specific task name or type, and days overdue. Example: "Task ID 41 — coordination milestone 47 days overdue, blocking EL and VVS trades." NEVER use vague language. NEVER omit the ID.

- **will_block**: One sentence describing the downstream consequence if unresolved. Reference specific disciplines or areas. Example: "Unresolved, this will delay electrical and HVAC installation across Omr. 2 and Omr. 3 by at least 6–8 weeks."

- **prevent_action_now**: ≤10-word imperative starting with an action verb. Names who does what. Example: "Escalate ID 41 coordination meeting to project director today." FORBIDDEN words: "monitor", "consider", "review", "look into", "assess", "evaluate". Must be in the response language."""


PREDICTIVE_LANGUAGE_INSTRUCTIONS = {
    "da": """
IMPORTANT: All descriptive text must be in Danish (Dansk):
- executive_actions[].action: written in Danish — direct instructions
- executive_actions[].responsible: written in Danish (e.g. "Projektleder", "Designleder", "Bygherre")
- executive_actions[].deadline: written in Danish with REAL day name and date (e.g. "Torsdag d. 3. april 2026", "Senest fredag d. 4. april")
- executive_actions[].manpower_note: written in Danish
- management_conclusion: written in Danish
- priority_actions[].action: written in Danish
- resource_assessment[].assessment: written in Danish
- forcing_assessment[].reason: written in Danish
- forcing_assessment[].risk_if_forced: written in Danish
- forcing_assessment[].recommendation: written in Danish
- forcing_assessment[].point_of_no_return: written in Danish
- summary_by_area[].summary: written in Danish
- root_cause_analysis[].why_it_matters, downstream_impact, consequence_if_unresolved: Danish
- predictive_snapshot.what_will_happen: written in Danish — start with "Hvis der ikke handles, ..."
- predictive_snapshot.confidence_basis: written in Danish
- predictive_snapshot.main_delay_drivers[]: written in Danish — short bullets
- predictive_biggest_risk.risk_title: written in Danish
- predictive_biggest_risk.will_block: written in Danish
- predictive_biggest_risk.prevent_action_now: written in Danish — imperative verb phrase
- Keep task_name values in their ORIGINAL language from the PDF (do not translate)
- human_label must be written in DANISH — 2–4 ord på dansk der beskriver opgaven for en ikke-teknisk projektleder
- Enum values (task_type, priority, problem_type, resource_type, action_type, is_forceable, constraint_type, coordination_cost, parallelizability, confidence_level) stay in English — these are machine-readable
""",
    "en": """
Respond with all descriptive text in English.
Keep task_name values in their original language from the PDF (do not translate).
human_label must be written in ENGLISH — 2–4 plain English words describing the task for a non-technical project manager.
Enum values stay as defined in the schema.
"""
}


_NUSF_PREDICTIVE_FORMAT_SECTION = """## DATA FORMAT: NUSF (Pre-Normalized)

The schedule data has been pre-normalized to NUSF (Normalized Unified Schedule Format).
You do NOT need to detect document types or map column names — all fields are already standardized.

NUSF CSV format: semicolon-separated, each row = one activity.
Each chunk begins with: "FORMAT: NUSF CSV — each row = one activity."

| Field | Meaning | Notes |
|-------|---------|-------|
| `source_id` | Task identifier (content-hash; stable for the same activity across runs) | Use as the `id` field in your JSON output. Never empty. The hash is content-derived: same logical input → same hash. |
| `name` | Task name / description | Already human-readable |
| `planned_start` | Planned start date | dd-mm-yyyy |
| `planned_finish` | Planned finish date | dd-mm-yyyy |
| `percent_complete` | Completion percentage | 0.0–100.0; use for delay detection |
| `activity_type` | Task classification | TASK / SUMMARY / MILESTONE / LOE |
| `wbs_code` | Work breakdown structure code | Use for area/hierarchy context; empty if not available |
| `discipline` | Trade or discipline | e.g. EL, VVS, Ventilation; use as area and responsible party |
| `duration_hours` | Duration in working hours | 8h ≈ 1 working day; 0 = milestone |
| `actual_start` | Actual start date | dd-mm-yyyy or empty if not yet started |
| `actual_finish` | Actual finish date | dd-mm-yyyy or empty if not yet complete |

### Delay Detection (NUSF):
An activity is DELAYED if BOTH are true:
1. `planned_start` < reference_date (compare date parts only — dd-mm-yyyy)
2. `percent_complete = 0.0` (not started)

ALSO delayed if: `actual_start` is filled AND `actual_finish` is empty AND `planned_finish` < reference_date (started but not completed on time).

EXCLUDE from analysis:
- Rows where `activity_type = SUMMARY` (grouping headers)
- Rows where `percent_complete = 100.0` (fully complete)

Milestones (`activity_type = MILESTONE`, duration_hours = 0) with `planned_start` < reference_date and 0% are delayed — include them.

Task ID: use `source_id` as the `id` field. NEVER leave empty. NEVER use row numbers. The source_id is a content-derived hash; treat it as the unique activity identifier.
Area / zone: use `discipline` column value, or parse from `wbs_code` if `discipline` is empty.
Responsible party: use `discipline` column value.

"""


def _build_nusf_predictive_prompt() -> str:
    """Build NUSF-specific predictive system prompt.

    Replaces the raw-format AUTO-DETECT DOCUMENT TYPE, FORMAT 1-5,
    ADAPTIVE COLUMN MAPPING, FIELD DEFINITIONS, and RESPONSIBLE PARTY
    IDENTIFICATION sections with a short NUSF field reference.
    The AREA/ZONE STRUCTURE section and everything from </context> onward
    are kept intact.
    """
    auto_detect_marker = "## AUTO-DETECT DOCUMENT TYPE"
    area_zone_marker = "## AREA/ZONE STRUCTURE"

    before = PREDICTIVE_SYSTEM_PROMPT[: PREDICTIVE_SYSTEM_PROMPT.index(auto_detect_marker)]
    after_adaptive = PREDICTIVE_SYSTEM_PROMPT[PREDICTIVE_SYSTEM_PROMPT.index(area_zone_marker):]

    return before + _NUSF_PREDICTIVE_FORMAT_SECTION + after_adaptive


PREDICTIVE_SYSTEM_PROMPT_NUSF = _build_nusf_predictive_prompt()


# ============================================================================
# TL-5.4 — Narrative-only schema, prompt, and fact/narrative merge
# ============================================================================
# Brief §4/§17: "The LLM's job becomes: explain the truth, rather than
# discover/invent the truth." `NOVA_INSIGHT_SCHEMA` above (and the prompt
# feeding it) asks the model to detect delays, count activities, and invent
# per-activity facts from a raw text dump — precisely the anti-pattern this
# phase removes. `NOVA_NARRATIVE_SCHEMA` is deliberately smaller: every field
# is either free-text narrative or judgement (`forcing_assessment` — brief
# calls this "genuinely judgemental," TL-5.4 item 5) keyed by an `id` that
# must already appear in the supplied structured context
# (`src/trust/context.py`'s `build_predictive_context`). No field in this
# schema can express a delay count, a date, or an activity's existence —
# those come from `build_response_facts` and are merged in afterward by
# `_merge_narrative_into_facts`, never asked of the model.
#
# `human_label` (the old schema's per-activity plain-language rename) is not
# part of this schema at all. The old prompt asked the model to label every
# activity in `delayed_activities`; but the new structured context shows the
# model only a bounded handful (`actionable_activities` +
# `biggest_risk_candidate`) — most delayed activities are never in its
# context, so it cannot honestly label them. Rather than build a second,
# narrower labelling pass for just the bounded subset (real scope, not done
# here), `human_label` falls back to the real `task_name` everywhere
# (`build_response_facts`'s `_delayed_activity_fact`) until a later task
# deliberately reintroduces it — recorded as a known regression in
# `changes/trust-layer/plan/DECISIONS.md`, not a silent drop.

NOVA_NARRATIVE_SCHEMA = {
    "name": "nova_narrative_report",
    "strict": True,
    "schema": {
        "type": "object",
        "required": [
            "predictive_snapshot",
            "predictive_biggest_risk",
            "executive_actions",
            "management_conclusion",
            "root_cause_narratives",
            "priority_actions",
            "resource_assessment",
            "forcing_assessment",
            "summary_by_area_narratives",
            "insight_narrative",
        ],
        "additionalProperties": False,
        "properties": {
            "predictive_snapshot": NOVA_INSIGHT_SCHEMA["schema"]["properties"]["predictive_snapshot"],
            "predictive_biggest_risk": NOVA_INSIGHT_SCHEMA["schema"]["properties"]["predictive_biggest_risk"],
            "executive_actions": NOVA_INSIGHT_SCHEMA["schema"]["properties"]["executive_actions"],
            "management_conclusion": NOVA_INSIGHT_SCHEMA["schema"]["properties"]["management_conclusion"],
            "root_cause_narratives": {
                "type": "array",
                "description": "Narrative text ONLY, one entry per root-cause `id` that appears in the supplied `biggest_risk_candidate` or `actionable_activities`. Do NOT invent an id that is not present there. Do NOT include an entry for any id not supplied.",
                "items": {
                    "type": "object",
                    "required": ["id", "why_it_matters", "downstream_impact", "consequence_if_unresolved"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string", "description": "Must exactly match an id from the supplied context. Never invent an id."},
                        "why_it_matters": {"type": "string", "description": "1 sentence: what does this block or prevent"},
                        "downstream_impact": {"type": "string", "description": "Which disciplines/areas are affected, or 'Isolated' if none — use the supplied `affected_count`, do not invent task names you were not given"},
                        "consequence_if_unresolved": {"type": "string", "description": "1 sentence: what happens if this stays unresolved"},
                    },
                },
            },
            "priority_actions": NOVA_INSIGHT_SCHEMA["schema"]["properties"]["priority_actions"],
            "resource_assessment": {
                "type": "array",
                "description": "One entry per id in the supplied `actionable_activities` with priority CRITICAL_NOW. Do NOT invent an id.",
                "items": {
                    "type": "object",
                    "required": ["id", "resource_type", "assessment"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string", "description": "Must exactly match an id from the supplied `actionable_activities`. Never invent an id."},
                        "resource_type": {"type": "string", "enum": ["coordination_bottleneck", "design_dependency", "bygherre_escalation", "production_manpower", "management_attention", "procurement_dependency"]},
                        "assessment": {"type": "string", "description": "1-2 sentences: whether adding labour helps, whether management attention is needed, whether prerequisites must be resolved first"},
                    },
                },
            },
            "forcing_assessment": {
                "type": "array",
                "description": "One entry per id in the supplied `actionable_activities` (CRITICAL_NOW and IMPORTANT_NEXT only — skip MONITOR, which never appears in `actionable_activities` anyway). Do NOT invent an id.",
                "items": {
                    "type": "object",
                    "required": [
                        "id", "is_forceable", "constraint_type", "reason", "risk_if_forced",
                        "recommendation", "coordination_cost", "parallelizability",
                        "max_speedup_factor", "optimal_team_size", "point_of_no_return",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string", "description": "Must exactly match an id from the supplied `actionable_activities`. Never invent an id."},
                        **{
                            k: v
                            for k, v in NOVA_INSIGHT_SCHEMA["schema"]["properties"]["forcing_assessment"]["items"]["properties"].items()
                            if k not in ("id", "task_name", "human_label")
                        },
                    },
                },
            },
            "summary_by_area_narratives": {
                "type": "array",
                "description": "One entry per area named in the supplied `clusters`. `area` must exactly match a `clusters[].location` value from the supplied context.",
                "items": {
                    "type": "object",
                    "required": ["area", "summary"],
                    "additionalProperties": False,
                    "properties": {
                        "area": {"type": "string", "description": "Must exactly match a `clusters[].location` value from the supplied context."},
                        "summary": {"type": "string", "description": "1-sentence situation summary for this area including forcing viability note"},
                    },
                },
            },
            "insight_narrative": {
                "type": "object",
                "required": ["primary_risk", "critical_findings", "consequences_if_no_action"],
                "additionalProperties": False,
                "properties": {
                    "primary_risk": {"type": "string", "description": "Short description of the primary risk driver, grounded in the supplied `biggest_risk_candidate`/`clusters`"},
                    "critical_findings": NOVA_INSIGHT_SCHEMA["schema"]["properties"]["insight_data"]["properties"]["critical_findings"],
                    "consequences_if_no_action": NOVA_INSIGHT_SCHEMA["schema"]["properties"]["insight_data"]["properties"]["consequences_if_no_action"],
                },
            },
        },
    },
}


PREDICTIVE_NARRATIVE_SYSTEM_PROMPT = """<context>
You are Nova Insight — a senior construction schedule analyst and decision support system.

You are given a STRUCTURED, VERIFIED set of facts about a construction schedule. These facts were
computed deterministically in code from the schedule's own data — they are not your output to produce,
and they are not open to revision. Your job is DIFFERENT from before: you do not detect delays, you do
not count activities, you do not decide which activities exist or which are root causes. All of that is
already decided and supplied to you. Your job is to EXPLAIN, PRIORITISE, and ADVISE, grounded strictly
in what you were given.

## THE STRUCTURED CONTEXT YOU RECEIVE

- `reference_date`: the date all overdue calculations are measured against.
- `project_status`: aggregate counts (`delayed_activities`, `critical_delayed`, `important_delayed`,
  `monitor_delayed`, `root_cause_count`, `unverified_delayed_count`) and a `confidence` word
  ("high"/"medium"). These numbers are FINAL — never restate them differently, never recompute them.
- `clusters[]`: confirmed delayed activities grouped by `location` x `trade`, each with `delayed`,
  `critical` counts and its own `confidence`.
- `biggest_risk_candidate`: the single highest-impact confirmed root cause (`id`, `name`, `days_overdue`,
  `affected_count`, `location`, `trade`, `trust_state`), or `null` if there is no confirmed root cause to
  name.
- `actionable_activities[]`: the bounded set of confirmed root-cause / CRITICAL_NOW / IMPORTANT_NEXT
  activities you may write about individually (`id`, `name`, `days_overdue`, `priority`, `is_root_cause`,
  `blocked_by_id`, `affected_count`, `location`, `trade`), plus `actionable_activities_omitted_count` —
  how many more exist beyond this bounded list (never silently ignore this number; if it is greater than
  zero, your narrative must not imply `actionable_activities` is the complete list of problems).

## THE ABSOLUTE RULE

Every activity `id` you write ANYWHERE in your response (`root_cause_narratives[].id`,
`resource_assessment[].id`, `forcing_assessment[].id`, `executive_actions[].related_task_ids[]`) MUST be
copied EXACTLY from an `id` that appears in `biggest_risk_candidate` or `actionable_activities` above.

NEVER invent an id. NEVER guess an id. NEVER reference an activity you were not given an id for — if you
need to talk about activities beyond what you were shown, refer to them only in aggregate terms using the
supplied counts (e.g. "12 further activities in Area 2 are affected" — a number from `project_status` or
`clusters`, never a name or id you were not given).

If `biggest_risk_candidate` is `null`, there is no confirmed root cause to name — do not invent one; write
`predictive_biggest_risk` to state plainly that no single dominant root cause could be confirmed yet and
what would need to happen to identify one (validation, more data), naming zero ids.

</context>

<task>
## FORCING ASSESSMENT (Module F) — for every entry in `actionable_activities` (CRITICAL_NOW / IMPORTANT_NEXT
only — the supplied list already excludes MONITOR), evaluate whether the activity can be accelerated by
adding resources, and what happens if the PM tries anyway. This is the one part of the analysis that stays
genuinely judgemental — there is no deterministic answer to "should the PM force this."

### FORCING ASSESSMENT RULES (RULE-BASED LOGIC):

RULE 1 — COORDINATION / DESIGN / BYGHERRE CONSTRAINTS: is_forceable="not_recommended", the constraint is a
missing decision or input that manpower cannot resolve, coordination_cost="high", parallelizability="low",
max_speedup_factor="1.0x", optimal_team_size="N/A".

RULE 2 — PROCUREMENT: is_forceable="not_recommended", constraint_type="procurement_waiting", manpower has
no effect until materials arrive, coordination_cost="low", parallelizability="low", max_speedup_factor="1.0x",
optimal_team_size="N/A".

RULE 3 — PRODUCTION with many downstream dependencies (`affected_count` > 3): is_forceable="limited",
constraint_type="cascading_dependencies", errors will cascade through multiple trades,
max_speedup_factor="1.5x-2.0x", optimal_team_size="2-4 people".

RULE 4 — PRODUCTION with few/no downstream dependencies (`affected_count` <= 3): is_forceable="possible",
constraint_type="execution_capacity", diminishing returns apply but acceleration is viable,
max_speedup_factor="2.0x-3.0x" for high parallelizability / "1.5x-2.0x" for medium.

RULE 5 — MILESTONES (zero-duration coordination/decision gates): is_forceable="not_recommended",
constraint_type="milestone_gate", max_speedup_factor="1.0x", optimal_team_size="N/A".

TRADE-SPECIFIC COORDINATION COST GUIDANCE (use `trade` from the supplied activity):
Revit/BIM modeling: high/low. Electrical: low/high. HVAC/VVS: medium/medium. Carpentry/finishing: low/high.
Painting/surface: low/high. Concrete/structural: medium/medium. Design/engineering: high/low.
Cross-discipline coordination: high/low.

POINT OF NO RETURN: "Already past — resolve constraint first" if severely overdue and not_recommended;
"Approaching — act within X days" if limited and getting close; "Still recoverable — forcing window open"
if possible and days_overdue is manageable; state the prerequisite for non-forceable tasks.

## EXECUTIVE ACTIONS — EXACTLY 3, ranked by urgency, synthesised from `biggest_risk_candidate`,
`actionable_activities`, and your own forcing assessment. Each is a direct instruction: WHO, WHAT, WHEN
(use the real day names/dates given in the user message), and whether manpower helps or is USELESS.
Any `related_task_ids` you cite must come from `actionable_activities`/`biggest_risk_candidate`.

## PREDICTIVE SNAPSHOT — synthesise `what_will_happen` / `estimated_delay_impact` from
`project_status.delayed_activities`/`critical_delayed` and the worst `days_overdue` you were given in
`actionable_activities`/`biggest_risk_candidate`. When `project_status.delayed_activities` is 0, do not
fabricate a delay window — describe structural risk only, per the field's own description below.
`confidence_level` should reflect `project_status.confidence` (map "high"→HIGH, "medium"→MEDIUM; if
`project_status.confidence` is null, use LOW). `main_delay_drivers` must reference only the supplied
`clusters`/`actionable_activities` — never invent a category with no supplied evidence.

## SUMMARY BY AREA — one narrative sentence per `clusters[].location`, matching the `area` field exactly to
that location string, referencing that cluster's own `delayed`/`critical`/`confidence`.

## LANGUAGE

`management_conclusion`, narrative text fields, and enum fields stay as documented in the language
instructions appended below. Enum values themselves (task_type, priority, is_forceable, constraint_type,
coordination_cost, parallelizability, confidence_level, resource_type) always stay in English — they are
machine-readable.

## HEDGING — BRIEF §20

Brief §20: *"Never make a prediction visually indistinguishable from an observed fact."* The phrasing
matters to construction professionals. Apply these rules:

- **Forecasts and inferences** (`predictive_snapshot.what_will_happen`, `estimated_delay_impact`,
  `predictive_biggest_risk.will_block`, `main_delay_drivers`, etc.) MUST use hedged language:
  *"shows a pattern of"*, *"indicates"*, *"is consistent with"*, *"is associated with"*, *"the
  largest concentration of current delay is within"* — never *will be*, *caused by*, *due to*,
  *definitely*, *always*, *never*.
- **Verified facts and deterministic counts** (`delayed_activities[].id`, `start_date`, `days_overdue`,
  `insight_data.delayed_count`, `schedule_overview.*`) MUST speak directly — no hedging on
  numbers that come straight from the source. *"Task ID 41 is delayed by 47 days"* is correct;
  hedging it to *"Task ID 41 appears to be delayed"* is over-cautious and erodes trust in the
  labels themselves.
- **Causal claims** (`A is caused by B`, *X led to Y*) are NEVER supported by schedule data —
  the schedule records *what* and *when*, never *why*. Even if your pattern-matching suggests a
  cause, phrase it associatively: *"the largest concentration of current delay is within electrical
  activities"*, not *"electrical work caused the delay"*.

A deterministic post-generation check (`TL-6.6`, brief §34 enforcement architecture) will rewrite
overclaiming phrasing on INFERENCE-classified text to its hedged form before the response reaches the
renderer. The prompt is the last layer; the check is the gate. Both must be present. If your first
draft uses hedged phrasing throughout, the check will pass cleanly with zero rewrites.

## DANISH (when `language="da"`)

The same hedging rules apply, with Danish equivalents — *forårsaget af* → *forbundet med*;
*vil blive forsinket* → *viser et mønster af forsinkelse*; *helt sikkert* → *sandsynligvis*; etc.
Kemp is Danish-only (brief §46); the Danish hedging rewrite must be just as strict as the English.

Return complete JSON matching the strict schema.
</task>"""


PREDICTIVE_NARRATIVE_LANGUAGE_INSTRUCTIONS = {
    "da": """
IMPORTANT: All narrative text must be in Danish (Dansk):
- executive_actions[].action/.responsible/.deadline/.manpower_note: Danish, with REAL day names and dates
- management_conclusion: Danish
- priority_actions[].action: Danish
- resource_assessment[].assessment: Danish
- forcing_assessment[].reason/.risk_if_forced/.recommendation/.point_of_no_return: Danish
- summary_by_area_narratives[].summary: Danish
- root_cause_narratives[].why_it_matters/.downstream_impact/.consequence_if_unresolved: Danish
- predictive_snapshot.what_will_happen: Danish — start with "Hvis der ikke handles, ..."
- predictive_snapshot.confidence_basis / .main_delay_drivers[]: Danish
- predictive_biggest_risk.risk_title/.will_block/.prevent_action_now: Danish
- insight_narrative.primary_risk/.critical_findings[]/.consequences_if_no_action[]: Danish
- Enum values stay in English.
""",
    "en": """
Respond with all narrative text in English. Enum values stay as defined in the schema.
""",
}


# ============================================================================
# TL-5.6 — FORECAST/FACT separation: per-field `EvidenceClass` annotations
# ============================================================================
# Brief §31, §45 — observed facts and forward-looking predictions must never
# look identical to a reader. Every leaf in the response carries an
# `EvidenceClass` (SOURCE_DATA / NOVA_CALCULATION / NOVA_INSIGHT /
# NOVA_FORECAST), exposed as a sibling `_classification` map at the top
# level of the merged response. The map shape is:
#
#     {
#       "<section_name>": {                  # e.g. "delayed_activities"
#         "<field_name>": "<class>",         # applied to every item
#         ...
#       },
#       "<section_name>": "<class>",         # for top-level scalars
#       ...
#     }
#
# This is the *minimum* representation that satisfies the brief's "every
# schema element carries an EvidenceClass" AC: a flat per-leaf map keys
# off the response's own shape, so `tests/trust/test_forecast_classification.py`
# can walk the response and assert every (section, field) is covered —
# catching drift between the schema and the classification map.
#
# Classification rules (rationale per class, brief §45):
# - SOURCE_DATA — values lifted verbatim from the schedule. Activity ids,
#   names, dates, durations, progress, area/discipline. Trust discipline
#   here is the source itself (Phase 1); the response does not transform.
# - NOVA_CALCULATION — deterministic derivations in Python (`days_overdue`,
#   `priority`, `task_type`, `is_root_cause`, all `insight_data` counts).
#   The model is never asked to produce these (brief §4, §15).
# - NOVA_INSIGHT — the model's interpretive judgement on observed data
#   (forcing viability, root-cause `why_it_matters`, resource assessment,
#   the `summary` sentence per area, action `responsible`/`manpower_note`).
#   Grounded in the data, not forward-looking.
# - NOVA_FORECAST — forward-looking predictions. `predictive_snapshot.*`,
#   `predictive_biggest_risk.will_block` / `.prevent_action_now`,
#   `executive_actions[].action`, `priority_actions[].action`. Brief §31
#   holds these to a higher bar than observations.
#
# NOTE — the "Do not" rule: do not classify the zero-delay structural-risk
# narrative as a forecast about delay. It is an inference about structure
# (brief §20) — the *field* `predictive_snapshot.what_will_happen` is
# classified NOVA_FORECAST because that is what it is intended to hold;
# when `delayed_count == 0` the *value* is structurally an inference, and
# `_build_classification` would re-classify it on inspection of the
# `insight_data.delayed_count` if asked. We deliberately do not encode
# that re-classification here — it is the renderer's job (TL-7.4) to
# treat "If no action is taken..." prose differently when no delays
# exist. The classification is on the field, not on its current value.
#
# AC3 ("no element defaults to SOURCE_DATA implicitly") is enforced by
# the test's `test_explicit_classifications_only`: every entry in this
# map is named; there is no fallback. A field that is *not* in this map
# will trip `_build_classification`'s validation error, surfacing the
# gap as a test failure rather than silently defaulting to SOURCE_DATA.
FIELD_EVIDENCE_CLASSIFICATIONS: dict = {
    # Top-level scalars
    "management_conclusion": EvidenceClass.NOVA_INSIGHT,
    # predictive_snapshot — every field is a forecast or insight (brief §31)
    "predictive_snapshot": {
        "what_will_happen": EvidenceClass.NOVA_FORECAST,
        "estimated_delay_impact": EvidenceClass.NOVA_FORECAST,
        "confidence_level": EvidenceClass.NOVA_CALCULATION,  # HIGH/MEDIUM/LOW is rule-based
        "confidence_basis": EvidenceClass.NOVA_INSIGHT,      # model's reasoning about confidence
        "main_delay_drivers": EvidenceClass.NOVA_INSIGHT,    # model categorisation
    },
    # predictive_biggest_risk — title is framing, will_block/prevent are forecasts
    "predictive_biggest_risk": {
        "risk_title": EvidenceClass.NOVA_INSIGHT,
        "will_block": EvidenceClass.NOVA_FORECAST,
        "prevent_action_now": EvidenceClass.NOVA_FORECAST,
    },
    # executive_actions — TOP 3 imperative moves; rank/responsible/manpower are insight, action is forecast
    "executive_actions": {
        "rank": EvidenceClass.NOVA_INSIGHT,
        "action": EvidenceClass.NOVA_FORECAST,
        "responsible": EvidenceClass.NOVA_INSIGHT,
        "deadline": EvidenceClass.NOVA_CALCULATION,  # derived from today's date
        "related_task_ids": EvidenceClass.SOURCE_DATA,
        "manpower_helps": EvidenceClass.NOVA_INSIGHT,
        "manpower_note": EvidenceClass.NOVA_INSIGHT,
    },
    # schedule_overview — counts are calculated, names/dates are source
    "schedule_overview": {
        "schedule_name": EvidenceClass.SOURCE_DATA,
        "reference_date": EvidenceClass.SOURCE_DATA,
        "total_activities": EvidenceClass.NOVA_CALCULATION,
        "delayed_count": EvidenceClass.NOVA_CALCULATION,
        "areas_covered": EvidenceClass.SOURCE_DATA,
        "format_detected": EvidenceClass.NOVA_CALCULATION,
    },
    # delayed_activities — per-item, deterministic counts/types, source for ids/dates
    "delayed_activities": {
        "id": EvidenceClass.SOURCE_DATA,
        "task_name": EvidenceClass.SOURCE_DATA,
        "human_label": EvidenceClass.NOVA_INSIGHT,
        "start_date": EvidenceClass.SOURCE_DATA,
        "end_date": EvidenceClass.SOURCE_DATA,
        "duration": EvidenceClass.SOURCE_DATA,
        "progress": EvidenceClass.SOURCE_DATA,
        "days_overdue": EvidenceClass.NOVA_CALCULATION,
        "task_type": EvidenceClass.NOVA_CALCULATION,
        "priority": EvidenceClass.NOVA_CALCULATION,
        "is_root_cause": EvidenceClass.NOVA_CALCULATION,
        "blocked_by_id": EvidenceClass.SOURCE_DATA,
        "area": EvidenceClass.SOURCE_DATA,
    },
    # root_cause_analysis — source for ids, calculation for days/problem_type,
    # insight for the model's narrative ("why_it_matters" etc.)
    "root_cause_analysis": {
        "id": EvidenceClass.SOURCE_DATA,
        "task_name": EvidenceClass.SOURCE_DATA,
        "human_label": EvidenceClass.NOVA_INSIGHT,
        "days_overdue": EvidenceClass.NOVA_CALCULATION,
        "problem_type": EvidenceClass.NOVA_CALCULATION,
        "why_it_matters": EvidenceClass.NOVA_INSIGHT,
        "downstream_impact": EvidenceClass.NOVA_INSIGHT,
        "consequence_if_unresolved": EvidenceClass.NOVA_INSIGHT,
        "affected_task_ids": EvidenceClass.SOURCE_DATA,
    },
    # downstream_consequences — sourced from the dependency graph
    "downstream_consequences": {
        "id": EvidenceClass.SOURCE_DATA,
        "task_name": EvidenceClass.SOURCE_DATA,
        "human_label": EvidenceClass.NOVA_INSIGHT,
        "blocked_by_id": EvidenceClass.SOURCE_DATA,
    },
    # priority_actions — model's prioritised list of actions to take
    "priority_actions": {
        "step": EvidenceClass.NOVA_CALCULATION,
        "action": EvidenceClass.NOVA_FORECAST,
        "action_type": EvidenceClass.NOVA_CALCULATION,
    },
    # resource_assessment — model's interpretive judgement on resource bottlenecks
    "resource_assessment": {
        "id": EvidenceClass.SOURCE_DATA,
        "task_name": EvidenceClass.SOURCE_DATA,
        "human_label": EvidenceClass.NOVA_INSIGHT,
        "resource_type": EvidenceClass.NOVA_INSIGHT,
        "assessment": EvidenceClass.NOVA_INSIGHT,
    },
    # forcing_assessment — every field is a model judgement call (brief §4 keeps this with the model)
    "forcing_assessment": {
        "id": EvidenceClass.SOURCE_DATA,
        "task_name": EvidenceClass.SOURCE_DATA,
        "human_label": EvidenceClass.NOVA_INSIGHT,
        "is_forceable": EvidenceClass.NOVA_INSIGHT,
        "constraint_type": EvidenceClass.NOVA_INSIGHT,
        "reason": EvidenceClass.NOVA_INSIGHT,
        "risk_if_forced": EvidenceClass.NOVA_INSIGHT,
        "recommendation": EvidenceClass.NOVA_INSIGHT,
        "coordination_cost": EvidenceClass.NOVA_INSIGHT,
        "parallelizability": EvidenceClass.NOVA_INSIGHT,
        "max_speedup_factor": EvidenceClass.NOVA_INSIGHT,
        "optimal_team_size": EvidenceClass.NOVA_INSIGHT,
        "point_of_no_return": EvidenceClass.NOVA_INSIGHT,
    },
    # summary_by_area — counts are computed; the per-area `summary` is model prose
    "summary_by_area": {
        "area": EvidenceClass.SOURCE_DATA,
        "delayed_count": EvidenceClass.NOVA_CALCULATION,
        "critical_count": EvidenceClass.NOVA_CALCULATION,
        "important_count": EvidenceClass.NOVA_CALCULATION,
        "monitor_count": EvidenceClass.NOVA_CALCULATION,
        "summary": EvidenceClass.NOVA_INSIGHT,
    },
    # insight_data — almost entirely NOVA_CALCULATION (counts); narrative fields are insight
    "insight_data": {
        "total_activities": EvidenceClass.NOVA_CALCULATION,
        "delayed_count": EvidenceClass.NOVA_CALCULATION,
        "critical_count": EvidenceClass.NOVA_CALCULATION,
        "important_count": EvidenceClass.NOVA_CALCULATION,
        "monitor_count": EvidenceClass.NOVA_CALCULATION,
        "root_cause_count": EvidenceClass.NOVA_CALCULATION,
        "reference_date": EvidenceClass.SOURCE_DATA,
        "most_overdue_days": EvidenceClass.NOVA_CALCULATION,
        "areas_affected": EvidenceClass.NOVA_CALCULATION,
        "format_detected": EvidenceClass.NOVA_CALCULATION,
        "schedule_name": EvidenceClass.SOURCE_DATA,
        "primary_risk": EvidenceClass.NOVA_INSIGHT,
        "forceable_count": EvidenceClass.NOVA_CALCULATION,
        "not_forceable_count": EvidenceClass.NOVA_CALCULATION,
        "project_status": EvidenceClass.NOVA_CALCULATION,
        "risk_level": EvidenceClass.NOVA_CALCULATION,
        "unverified_delayed_count": EvidenceClass.NOVA_CALCULATION,  # built by build_response_facts
        "critical_findings": EvidenceClass.NOVA_INSIGHT,
        "consequences_if_no_action": EvidenceClass.NOVA_INSIGHT,
    },
}


def _build_classification(response: dict) -> dict:
    """TL-5.6: emit a per-(section, field) `EvidenceClass` map for `response`.

    Walks `response` and produces a nested dict matching the shape in
    `FIELD_EVIDENCE_CLASSIFICATIONS` — every (section, field) present in
    `response` is looked up in the master map and emitted with its class.

    AC3 (no implicit `SOURCE_DATA` default): if a (section, field) is
    present in `response` but missing from `FIELD_EVIDENCE_CLASSIFICATIONS`,
    this function raises `ValueError` rather than silently defaulting. The
    test pins the same property statically. Drift surfaces as a failure,
    not as a quiet re-classification.
    """
    classification: dict = {}
    for section_name, section_value in response.items():
        if section_name.startswith("_"):
            # Skip metadata keys (e.g., `_classification` itself if we ever re-run).
            continue
        classification_for_section = FIELD_EVIDENCE_CLASSIFICATIONS.get(section_name)
        if classification_for_section is None:
            raise ValueError(
                f"TL-5.6: section {section_name!r} is present in the response "
                f"but has no classification in FIELD_EVIDENCE_CLASSIFICATIONS. "
                f"Add an explicit entry — do not let it default."
            )
        if isinstance(classification_for_section, EvidenceClass):
            # Top-level scalar (e.g., `management_conclusion`).
            classification[section_name] = classification_for_section.value
            continue
        # Section is an object or an array of objects. Walk items.
        if isinstance(section_value, list):
            if not section_value:
                # Empty array — nothing to validate per item, but record
                # the field map so consumers know what classification WOULD
                # apply if items were present.
                classification[section_name] = {
                    field: cls.value for field, cls in classification_for_section.items()
                }
                continue
            first_item = section_value[0]
            if not isinstance(first_item, dict):
                raise ValueError(
                    f"TL-5.6: section {section_name!r} items must be dicts, "
                    f"got {type(first_item).__name__}"
                )
            classification[section_name] = {}
            for field_name in first_item.keys():
                if field_name not in classification_for_section:
                    raise ValueError(
                        f"TL-5.6: field {section_name!r}.{field_name!r} is present "
                        f"in the response but has no classification. Add an explicit entry."
                    )
                classification[section_name][field_name] = (
                    classification_for_section[field_name].value
                )
        elif isinstance(section_value, dict):
            classification[section_name] = {}
            for field_name in section_value.keys():
                if field_name not in classification_for_section:
                    raise ValueError(
                        f"TL-5.6: field {section_name!r}.{field_name!r} is present "
                        f"in the response but has no classification. Add an explicit entry."
                    )
                classification[section_name][field_name] = (
                    classification_for_section[field_name].value
                )
        else:
            # Section is a top-level scalar (e.g., `management_conclusion`).
            classification[section_name] = classification_for_section.value
    return classification


# ============================================================================
# TL-6.1 — wrap the merged response in the brief §33 contract
# ============================================================================


def _build_agent_response(
    parsed_json: dict,
    user_query: str = "",
    language: str = "en",
) -> AgentResponse:
    """TL-6.1 + TL-6.3 + TL-6.5: wrap a fully-merged predictive response
    (raw or NUSF path, both converge on the same flat shape) in
    `AgentResponse` before it is handed to `validate_agent_response`.

    - `supporting_facts` / `source_references` are drawn from Phase 5's
      deterministic facts (`insight_data`, `delayed_activities`) — never
      from narrative prose, so they cannot themselves be an unverified
      claim.
    - `inferences` are the response's own headline forward-looking /
      interpretive statements. These sections are already known to be
      `NOVA_INSIGHT`/`NOVA_FORECAST` (TL-5.6's `_classification`) rather
      than fact; this is a coarse, response-level echo of that signal, not
      the per-claim `ClaimKind` tagging `TL-6.4` will add.
    - `answer` / `unverified_claims` now come from `verify_narrative`
      (`TL-6.3`): every claim in `management_conclusion` is extracted
      (`TL-6.2`) and checked against `parsed_json` itself — the same dict
      is both the narrative source and the fact store, which is exactly
      right, since `insight_data`/`delayed_activities`/`summary_by_area`
      are deterministic (Phase 5) regardless of which agent produced the
      narrative around them. `CONTRADICTED` claims are removed from
      `answer` outright (never rewritten — this task's Do-not rule);
      `UNVERIFIABLE` claims (causal claims always land here, brief §20)
      populate `unverified_claims` for `TL-6.1`'s gate to qualify.

    TL-6.5: when `user_query` is supplied AND is a causal/unanswerable
    question (matches `is_causal_question`), AND the conclusion contains
    unverifiable claims, the response is upgraded to a structured
    no-answer (brief §18) instead of a normal answer with
    `unverified_claims`. Brief §18 is explicit: this is a feature, not
    a failure — the gate renders the three-part reassuring text and the
    app shows it as a normal result, not an error banner.
    """
    insight_data = parsed_json.get("insight_data", {}) or {}
    delayed_activities = parsed_json.get("delayed_activities", []) or []
    snapshot = parsed_json.get("predictive_snapshot", {}) or {}
    biggest_risk = parsed_json.get("predictive_biggest_risk", {}) or {}

    supporting_facts = []
    if "delayed_count" in insight_data:
        supporting_facts.append(f"{insight_data['delayed_count']} confirmed delayed activities")
    if insight_data.get("critical_count"):
        supporting_facts.append(f"{insight_data['critical_count']} classified CRITICAL_NOW")
    if insight_data.get("root_cause_count") is not None:
        supporting_facts.append(f"{insight_data['root_cause_count']} confirmed root cause(s)")

    source_references = [a["id"] for a in delayed_activities if a.get("id")]

    inferences = merge_inferences(
        [snapshot.get("what_will_happen", "")],
        [biggest_risk.get("will_block", "")],
        [parsed_json.get("management_conclusion", "")],
    )

    verification = verify_narrative(parsed_json.get("management_conclusion", ""), parsed_json)

    # TL-6.4 (brief §19): per-(section, field) `ClaimKind` map for everything
    # in the response that does NOT go through extraction — the LLM-attributed
    # fields (`forcing_assessment[]`, `predictive_biggest_risk.will_block`,
    # per-area `summary` sentences, etc.). Per-claim `kind` for extracted
    # narrative lives on each `VerifiedClaim` (TL-6.3) and is computed by
    # `_classify_claim`; this map is the *parallel* field-level echo that
    # travels in the payload for TL-7.3 to render (brief §31: "the
    # classification travels in the payload"). Same map for both NUSF and
    # raw paths — both converge on the same flat response shape.
    field_claim_kinds = build_field_claim_kinds(parsed_json)
    parsed_json["_claim_kinds"] = field_claim_kinds

    if not verification.decomposable:
        # The narrative could not be safely analyzed at all — the most
        # conservative state, not `REVIEW` (brief's "unknown = unverified,
        # never assumed fine").
        confidence_state = TrustState.UNVERIFIED
    elif verification.contradicted or verification.unverifiable:
        # Either a false claim was caught and removed, or something
        # remains that could not be checked — both are the honest middle
        # state, never `VERIFIED`.
        confidence_state = TrustState.REVIEW
    elif verification.verified:
        # Every claim found was checked and matched the fact store.
        confidence_state = TrustState.VERIFIED
    else:
        # No claims were found at all — nothing to point to as verified,
        # so this stays short of `VERIFIED` rather than defaulting to it.
        confidence_state = TrustState.REVIEW

    # TL-6.5: structured no-answer (brief §18). Detect AFTER the
    # supporting facts and unverifiable claims are computed — the
    # detector needs both. Both the default `user_query=""` and the
    # standard predictive query ("Execute full two-phase analysis...")
    # skip no-answer (the trigger list is causal-question-specific);
    # the path only fires when a future caller passes a user query that
    # actually asks for causality.
    no_answer = detect_no_answer(
        question=user_query,
        facts=supporting_facts,
        unverifiable_claims=verification.unverified_claim_texts,
        language=language,
    )

    return AgentResponse(
        answer=verification.cleaned_text,
        supporting_facts=supporting_facts,
        source_references=source_references,
        confidence_state=confidence_state,
        inferences=inferences,
        unverified_claims=verification.unverified_claim_texts,
        no_answer=no_answer,
    )


def _merge_narrative_into_facts(
    response_facts: dict,
    structured_context: dict,
    narrative: dict,
) -> dict:
    """TL-5.4: combine `build_response_facts`'s deterministic FACTS with the
    model's narrative-only response into the flat shape
    `NOVA_INSIGHT_SCHEMA` used to produce, so `format_predictive_as_html` /
    the dashboard renderers need no changes.

    Pure function — no LLM call, no I/O — so it is fully unit-testable
    against a hand-built fake `narrative` dict, including the adversarial
    case where the model names an id it was never given. Any id in
    `narrative` that does not appear in `response_facts["delayed_activities"]`
    is dropped (never merged in), and the drop is logged — this is the
    enforcement TL-5.4's acceptance criterion ("model output contains no
    activity ID absent from the supplied context") actually rests on; the
    prompt-level instruction is necessary but not sufficient (brief §34).
    """
    known_ids = {a["id"] for a in response_facts["delayed_activities"] if a.get("id") is not None}

    def _by_id(items: list[dict]) -> dict[str, dict]:
        kept, dropped = {}, []
        for item in items:
            item_id = item.get("id")
            if item_id in known_ids:
                kept[item_id] = item
            else:
                dropped.append(item_id)
        if dropped:
            logger.warning(f"  [PredictiveAgent] Dropped {len(dropped)} narrative entr(y/ies) with unsupplied id(s): {dropped}")
        return kept

    facts_by_id = {a["id"]: a for a in response_facts["delayed_activities"] if a.get("id") is not None}

    root_cause_narratives = _by_id(narrative.get("root_cause_narratives", []))
    root_cause_analysis = []
    for fact in response_facts["root_cause_analysis"]:
        text = root_cause_narratives.get(fact["id"], {})
        root_cause_analysis.append({
            **fact,
            "why_it_matters": text.get("why_it_matters", _FALLBACK_NARRATIVE_TEXT),
            "downstream_impact": text.get("downstream_impact", _FALLBACK_NARRATIVE_TEXT),
            "consequence_if_unresolved": text.get("consequence_if_unresolved", _FALLBACK_NARRATIVE_TEXT),
        })

    resource_assessment = []
    for item in _by_id(narrative.get("resource_assessment", [])).values():
        fact = facts_by_id.get(item["id"], {})
        resource_assessment.append({
            "id": item["id"],
            "task_name": fact.get("task_name", ""),
            "human_label": fact.get("human_label", fact.get("task_name", "")),
            "resource_type": item.get("resource_type"),
            "assessment": item.get("assessment", _FALLBACK_NARRATIVE_TEXT),
        })

    forcing_assessment = []
    for item in _by_id(narrative.get("forcing_assessment", [])).values():
        fact = facts_by_id.get(item["id"], {})
        forcing_assessment.append({
            **{k: v for k, v in item.items()},
            "task_name": fact.get("task_name", ""),
            "human_label": fact.get("human_label", fact.get("task_name", "")),
        })

    area_narratives = {row.get("area"): row for row in narrative.get("summary_by_area_narratives", [])}
    summary_by_area = [
        {**fact, "summary": area_narratives.get(fact["area"], {}).get("summary", _FALLBACK_NARRATIVE_TEXT)}
        for fact in response_facts["summary_by_area"]
    ]

    forceable = sum(1 for f in forcing_assessment if f.get("is_forceable") in ("possible", "limited"))
    not_forceable = sum(1 for f in forcing_assessment if f.get("is_forceable") == "not_recommended")

    biggest_risk_candidate = structured_context.get("biggest_risk_candidate")
    predictive_biggest_risk = narrative.get("predictive_biggest_risk", {})
    if biggest_risk_candidate is None:
        # No confirmed root cause exists — the model was told not to invent
        # one; override defensively rather than trust free text here, since
        # there is nothing to ground it against.
        predictive_biggest_risk = dict(_NO_ROOT_CAUSE_RISK)

    insight_narrative = narrative.get("insight_narrative", {})
    insight_data = {
        **response_facts["insight_data"],
        "forceable_count": forceable,
        "not_forceable_count": not_forceable,
        "primary_risk": insight_narrative.get("primary_risk", _FALLBACK_NARRATIVE_TEXT),
        "critical_findings": insight_narrative.get("critical_findings", []),
        "consequences_if_no_action": insight_narrative.get("consequences_if_no_action", []),
    }

    merged = {
        "predictive_snapshot": narrative.get("predictive_snapshot", {}),
        "predictive_biggest_risk": predictive_biggest_risk,
        "executive_actions": [
            {**a, "related_task_ids": [t for t in a.get("related_task_ids", []) if t in known_ids]}
            for a in narrative.get("executive_actions", [])
        ],
        "management_conclusion": narrative.get("management_conclusion", ""),
        "schedule_overview": response_facts["schedule_overview"],
        "delayed_activities": response_facts["delayed_activities"],
        "root_cause_analysis": root_cause_analysis,
        "downstream_consequences": response_facts["downstream_consequences"],
        "priority_actions": narrative.get("priority_actions", []),
        "resource_assessment": resource_assessment,
        "forcing_assessment": forcing_assessment,
        "summary_by_area": summary_by_area,
        "insight_data": insight_data,
    }
    # TL-5.6 (brief §31, §45): per-leaf `EvidenceClass` map, built from the
    # exact dict being returned (not a second copy of the literal above) —
    # classifying a stale duplicate would silently drift from what the
    # caller actually receives the moment one copy is edited and the other
    # is not, which is exactly the kind of undetected mismatch TL-5.6
    # exists to prevent. Mirrors `analyze()`'s raw-path pattern: classify
    # before attaching `_classification` itself (the classifier already
    # skips `_`-prefixed keys, so call order here is not load-bearing, but
    # matching the other path's order keeps the two call sites symmetric).
    merged["_classification"] = _build_classification(merged)
    return merged


_FALLBACK_NARRATIVE_TEXT = "Detailed explanation not available for this item — see aggregate risk summary."

_NO_ROOT_CAUSE_RISK = {
    "risk_title": "No single dominant root cause confirmed",
    "will_block": "No confirmed root cause could be identified from the current data; downstream impact cannot be attributed to a specific activity yet.",
    "prevent_action_now": "Validate schedule dependencies to identify a root cause",
}


class PredictiveAgent:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
        self.deployment = settings.AZURE_OPENAI_PREDICTIVE_DEPLOYMENT
        logger.info(f"PredictiveAgent initialized with model: {self.deployment}")

    def analyze(
        self,
        context: str,
        user_query: str,
        language: str = "en",
        schedule_filename: str = None,
        reference_date: str = None,
        data_format: str = "raw",
    ) -> dict:
        logger.info(f"  [PredictiveAgent] Starting analysis with {self.deployment} (strict JSON schema)...")

        lang_instruction = PREDICTIVE_LANGUAGE_INSTRUCTIONS.get(
            language, PREDICTIVE_LANGUAGE_INSTRUCTIONS["en"]
        )
        base_prompt = PREDICTIVE_SYSTEM_PROMPT_NUSF if data_format == "nusf" else PREDICTIVE_SYSTEM_PROMPT
        logger.info(f"  [PredictiveAgent] Prompt variant: {'NUSF (pre-normalized)' if data_format == 'nusf' else 'RAW (original columns)'}")
        system_prompt = f"{base_prompt}\n\n{lang_instruction}"

        schedule_label = schedule_filename if schedule_filename else "Schedule"

        cet = timezone(timedelta(hours=1))
        today = datetime.now(cet).date()
        da_days = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
        en_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        da_months = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november", "december"]
        en_months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        if language == "da":
            today_str = f"{da_days[today.weekday()]} d. {today.day}. {da_months[today.month - 1]} {today.year}"
        else:
            today_str = f"{en_days[today.weekday()]}, {en_months[today.month - 1]} {today.day}, {today.year}"
        today_iso = today.strftime("%d-%m-%Y")

        ref_date_instruction = ""
        if reference_date:
            ref_date_instruction = f"""
REFERENCE DATE (MANDATORY): {reference_date}
This date was extracted from the uploaded filename. You MUST use this exact date as the reference date for all overdue calculations.
Do NOT use any other date. Do NOT use today's date. Use: {reference_date}
"""

        if data_format == "nusf":
            critical_instructions = """\
CRITICAL INSTRUCTIONS (NUSF format):
1. The data above is pre-normalized NUSF CSV (v2.0). Every row = one activity. No OCR artefacts.
2. Column headers: source_id | name | planned_start | planned_finish | percent_complete | activity_type | wbs_code | discipline | duration_hours | actual_start | actual_finish
3. Use the "source_id" column value as the "id" field in your JSON output. Never leave it empty. The source_id is a content-derived hash; same logical activity → same hash.
4. Use "percent_complete" (0.0–100.0) as the progress indicator.
5. Use "planned_start" (dd-mm-yyyy) as the start date for overdue calculations.

PHASE 1 — FIND ALL DELAYED ACTIVITIES:
- A row is delayed if: planned_start < reference_date AND percent_complete = 0.0
- Also delayed if: actual_start is filled AND actual_finish is empty AND planned_finish < reference_date
- Include ALL such rows. If there are 30 delayed activities, output all 30. If there are 50, output all 50.
- Do NOT limit to 4 or 5. Scan EVERY row. Include activities from ALL disciplines/areas.
- Only skip rows where activity_type = SUMMARY (grouping headers) or percent_complete = 100.0."""
        else:
            critical_instructions = """\
CRITICAL INSTRUCTIONS:
1. The data above is a COMPLETE markdown table extracted from the PDF via OCR. Every row is included.
2. The table has column headers in the first row (e.g. Id, Opgavenavn, Varighed, Startdato, Slutdato, % arbejde færdigt, etc.)
3. Read the "Id" column value for each row. Output that value in the "id" field.
4. The "% arbejde færdigt" (or similar) column contains the progress percentage.
5. The "Startdato" column contains the start date. Dates may be in formats like "ma 05-01-26", "ti 16-12-25", etc.

PHASE 1 — FIND ALL DELAYED ACTIVITIES:
- A row is delayed if: Startdato < reference_date AND progress = 0%
- Include ALL such rows. If there are 30 delayed activities, output all 30. If there are 50, output all 50.
- Do NOT limit to 4 or 5. Scan EVERY row. Include activities from ALL areas (Omr. 1, Omr. 2, Omr. 3, etc.)
- Activities from year 2025, 2024, 2023, etc. with 0% are ALL delayed relative to a 2026 reference date.
- Multiple activities with the same start date? Include ALL of them if they have 0%.
- Only skip grouping/summary headers (e.g. section headers like "Omr. 1", "E100.XX", "Globals", "Afhængigheder", "Færdiggøre projektering")."""

        user_message = f"""Analyze the following construction schedule data.

TODAY'S DATE: {today_str} ({today_iso})
Today is {en_days[today.weekday()]}. Use this to set concrete deadlines in executive_actions (e.g. real day names and dates like "torsdag d. 3. april" or "Thursday, April 3").

Schedule filename: "{schedule_label}"
{ref_date_instruction}
═══════════════════════════════════════════════════════════
COMPLETE SCHEDULE DATA (ALL PAGES):
═══════════════════════════════════════════════════════════
{context}
═══════════════════════════════════════════════════════════

{critical_instructions}

PHASE 2 — DECISION SUPPORT:
- Classify each delayed activity by task_type
- Determine root causes vs downstream consequences
- Assign priority (CRITICAL_NOW / IMPORTANT_NEXT / MONITOR)
- Generate action recommendations
- Write management conclusion

PHASE 3 — FORCING ASSESSMENT:
- For each CRITICAL_NOW and IMPORTANT_NEXT delayed activity, evaluate:
  a) Is this activity suitable for acceleration (forcing)?
  b) What is the primary constraint preventing or limiting acceleration?
  c) What happens if the PM forces it anyway?
  d) What is the clear recommendation?
  e) What is the coordination cost level and parallelizability?
  f) What is the maximum realistic speedup?
  g) What is the optimal team size for efficiency > 70%?
  h) Has this activity passed the point of no return for forcing?
- Apply the rule-based forcing logic (Rules 1-5 from the system prompt)
- Output must be simple, clear, and leave zero room for misinterpretation
- This is what makes the product decision support, not just analysis

PHASE 4 — EXECUTIVE ACTIONS (TOP 3 PRIORITIES):
After completing all analysis, synthesize into EXACTLY 3 executive actions.
These are THE 3 most impactful things the PM must do RIGHT NOW.

Rules for executive_actions:
1. Each action is a DIRECT INSTRUCTION — not a finding, not an observation. Write it as a command.
   GOOD: "Indkald møde med designteam for at afslutte loftplacering i Omr. 2"
   BAD: "Der er forsinkelser i designinput for Omr. 2"
2. Each action must specify WHO is responsible (by role, not by name)
3. Each action must specify WHEN — use REAL day names and dates based on TODAY'S DATE provided above.
   GOOD (da): "Torsdag d. 3. april 2026", "Senest fredag d. 4. april", "Mandag d. 7. april"
   GOOD (en): "Thursday, April 3, 2026", "By Friday, April 4", "Monday, April 7"
   BAD: "This week", "Within 3 days", "ASAP" — these are too vague
   Use the real calendar: if today is Wednesday, the next working day is Thursday.
   Urgent actions = tomorrow or day after. Important actions = within the week. Lower = next Monday.
4. Each action must clearly state whether adding manpower helps or is USELESS
5. When manpower is useless, the manpower_note must be blunt:
   "Ekstra mandskab hjælper IKKE — dette er en beslutning, ikke en arbejdsopgave"
   "Adding people will NOT help — this is a decision bottleneck, not a work task"
6. When manpower helps, state HOW MANY and the expected speedup
7. Actions should address ROOT CAUSES, not symptoms. Fixing 1 root cause may resolve 5 downstream delays.
8. Rank by impact: the action that unblocks the most downstream work = rank 1

Return complete JSON matching the strict schema."""

        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        logger.info(f"  [PredictiveAgent] LLM input ready (system={len(system_prompt)} chars, user={len(user_message)} chars)")

        try:
            api_params = {
                "model": self.deployment,
                "messages": messages,
                "temperature": 0,
                "top_p": 0.1,
                "seed": 42,
                "max_tokens": 32768,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": NOVA_INSIGHT_SCHEMA
                }
            }

            response = self.client.chat.completions.create(**api_params)

            choice = response.choices[0]
            raw_content = choice.message.content or ""

            logger.info(f"  [PredictiveAgent] LLM response received ({len(raw_content)} chars)")

            model_used = getattr(response, 'model', self.deployment)
            usage = getattr(response, 'usage', None)
            usage_parts = []
            if usage:
                usage_parts.append(f"prompt={usage.prompt_tokens}")
                usage_parts.append(f"completion={usage.completion_tokens}")
                reasoning_tokens = getattr(usage, 'completion_tokens_details', None)
                if reasoning_tokens:
                    r_tokens = getattr(reasoning_tokens, 'reasoning_tokens', None)
                    if r_tokens is None and hasattr(reasoning_tokens, 'model_extra'):
                        r_tokens = reasoning_tokens.model_extra.get('reasoning_tokens')
                    if r_tokens is not None:
                        usage_parts.append(f"reasoning={r_tokens}")
            usage_info = f", tokens: {', '.join(usage_parts)}" if usage_parts else ""

            if not raw_content and hasattr(choice.message, 'refusal') and choice.message.refusal:
                logger.warning(f"  [PredictiveAgent] Model refused: {choice.message.refusal}")
                return {"predictive_insights": None, "model": self.deployment, "status": "error", "error": f"Model refused: {choice.message.refusal}"}

            if not raw_content:
                logger.warning(f"  [PredictiveAgent] Empty content. finish_reason={choice.finish_reason}")
                return {"predictive_insights": None, "model": self.deployment, "status": "error", "error": "Empty response from model"}

            try:
                parsed_json = json.loads(raw_content)
            except json.JSONDecodeError as je:
                logger.error(f"  [PredictiveAgent] JSON parse error: {je}")
                return {"predictive_insights": raw_content, "predictive_json": None, "model": self.deployment, "status": "error", "error": f"Invalid JSON: {je}"}

            required_keys = {"executive_actions", "management_conclusion", "schedule_overview", "delayed_activities",
                             "root_cause_analysis", "downstream_consequences", "priority_actions",
                             "resource_assessment", "forcing_assessment", "summary_by_area", "insight_data"}
            missing_keys = required_keys - set(parsed_json.keys())
            if missing_keys:
                logger.error(f"  [PredictiveAgent] Schema validation failed — missing keys: {missing_keys}")
                return {"predictive_insights": raw_content, "predictive_json": None, "model": self.deployment, "status": "error", "error": f"Schema validation failed: missing {missing_keys}"}

            if not isinstance(parsed_json.get("delayed_activities"), list):
                logger.error(f"  [PredictiveAgent] Schema validation failed — delayed_activities is not a list")
                return {"predictive_insights": raw_content, "predictive_json": None, "model": self.deployment, "status": "error", "error": "Schema validation failed: delayed_activities is not a list"}

            # --- TL-5.2 (brief §4, §15): SUPERSEDED, NOT YET REMOVED --------
            # Everything below in this method — the `days_overdue <= 0` prune,
            # the root-cause ratio "sanity fix" heuristics, and the
            # critical_findings/management_conclusion regex renumbering — is a
            # deterministic correction layer bolted onto LLM-invented facts.
            # `src/trust/predictive_facts.py` (`detect_delayed_activities` +
            # `compute_predictive_facts`) now computes the same facts directly
            # in Python, from the schedule's own dependency graph, with no
            # LLM step to correct after the fact.
            #
            # This code is intentionally still live: nothing in `src/main.py`
            # calls the new module yet (that wiring is `TL-5.3`/`TL-5.4`), so
            # this remains the only correction layer protecting the current
            # `/predictive` endpoint. Deleting it now — before its replacement
            # is actually in the request path — would remove a working safety
            # net for zero gain, which is a regression, not a supersession.
            # Scheduled for deletion in `TL-5.4` ("Demote predictive_agent to
            # interpretation-only"), the task that rewires the routes. See
            # `changes/trust-layer/plan/DECISIONS.md` ADR-018 for the full
            # reasoning and the plan-deviation record (`phase-5-predictive-facts.md`
            # TL-5.2's own text says "remove them"; this is a deliberate,
            # documented departure from that instruction, not an oversight).
            # ------------------------------------------------------------------
            original_count = len(parsed_json.get("delayed_activities", []))
            valid_delayed = [a for a in parsed_json["delayed_activities"] if a.get("days_overdue", 0) > 0]
            removed_count = original_count - len(valid_delayed)
            if removed_count > 0:
                removed_ids = [a.get("id", "?") for a in parsed_json["delayed_activities"] if a.get("days_overdue", 0) <= 0]
                logger.warning(f"  [PredictiveAgent] Post-validation: removed {removed_count} false positives with days_overdue <= 0: {removed_ids}")
                parsed_json["delayed_activities"] = valid_delayed
                if "schedule_overview" in parsed_json:
                    parsed_json["schedule_overview"]["delayed_count"] = len(valid_delayed)
                if "insight_data" in parsed_json:
                    parsed_json["insight_data"]["delayed_count"] = len(valid_delayed)
                    parsed_json["insight_data"]["critical_count"] = sum(1 for a in valid_delayed if a.get("priority") == "CRITICAL_NOW")
                    parsed_json["insight_data"]["important_count"] = sum(1 for a in valid_delayed if a.get("priority") == "IMPORTANT_NEXT")
                    parsed_json["insight_data"]["monitor_count"] = sum(1 for a in valid_delayed if a.get("priority") == "MONITOR")

                dc_list = parsed_json.get("downstream_consequences", [])
                if dc_list:
                    valid_dc = [dc for dc in dc_list if dc.get("blocked_by_id") not in set(removed_ids)]
                    if len(valid_dc) < len(dc_list):
                        logger.info(f"  [PredictiveAgent] Post-validation: removed {len(dc_list) - len(valid_dc)} downstream consequences linked to false positives")
                        parsed_json["downstream_consequences"] = valid_dc

                fa_list = parsed_json.get("forcing_assessment", [])
                if fa_list:
                    removed_id_set = set(removed_ids)
                    valid_fa = [fa for fa in fa_list if fa.get("id") not in removed_id_set]
                    if len(valid_fa) < len(fa_list):
                        logger.info(f"  [PredictiveAgent] Post-validation: removed {len(fa_list) - len(valid_fa)} forcing assessments linked to false positives")
                        parsed_json["forcing_assessment"] = valid_fa

                ea_list = parsed_json.get("executive_actions", [])
                if ea_list:
                    removed_id_set = set(removed_ids)
                    for ea in ea_list:
                        orig_ids = ea.get("related_task_ids", [])
                        cleaned = [tid for tid in orig_ids if tid not in removed_id_set]
                        if len(cleaned) < len(orig_ids):
                            ea["related_task_ids"] = cleaned
                    logger.info(f"  [PredictiveAgent] Post-validation: cleaned executive_actions task ID references")

                if "insight_data" in parsed_json:
                    fa_after = parsed_json.get("forcing_assessment", [])
                    parsed_json["insight_data"]["forceable_count"] = sum(1 for f in fa_after if f.get("is_forceable") in ["possible", "limited"])
                    parsed_json["insight_data"]["not_forceable_count"] = sum(1 for f in fa_after if f.get("is_forceable") == "not_recommended")

            fa_final = parsed_json.get("forcing_assessment", [])
            forceable = sum(1 for f in fa_final if f.get("is_forceable") in ["possible", "limited"])
            not_forceable = sum(1 for f in fa_final if f.get("is_forceable") == "not_recommended")

            delayed_list = parsed_json.get("delayed_activities", [])
            true_delayed = len(delayed_list)
            true_critical = sum(1 for a in delayed_list if a.get("priority") == "CRITICAL_NOW")
            true_important = sum(1 for a in delayed_list if a.get("priority") == "IMPORTANT_NEXT")
            true_monitor = sum(1 for a in delayed_list if a.get("priority") == "MONITOR")
            true_root_causes = sum(1 for a in delayed_list if a.get("is_root_cause"))
            rca_list = parsed_json.get("root_cause_analysis", [])
            dc_list_check = parsed_json.get("downstream_consequences", [])
            if true_root_causes >= true_delayed and true_delayed > 5:
                if len(rca_list) < true_delayed:
                    true_root_cause_count = len(rca_list)
                    logger.warning(f"  [PredictiveAgent] Root cause sanity fix: LLM marked {true_root_causes}/{true_delayed} as root causes (all). Using root_cause_analysis array length: {true_root_cause_count}")
                elif len(dc_list_check) > 0:
                    true_root_cause_count = true_delayed - len(dc_list_check)
                    logger.warning(f"  [PredictiveAgent] Root cause sanity fix: Using delayed-downstream: {true_delayed}-{len(dc_list_check)}={true_root_cause_count}")
                else:
                    true_root_cause_count = true_root_causes
            elif true_root_causes > true_delayed * 0.7 and true_delayed > 10 and len(rca_list) < true_root_causes:
                true_root_cause_count = len(rca_list)
                logger.warning(f"  [PredictiveAgent] Root cause sanity fix: {true_root_causes}/{true_delayed} (>70%) marked as root. Using root_cause_analysis array: {true_root_cause_count}")
            else:
                true_root_cause_count = true_root_causes
            unique_areas = set()
            for a in delayed_list:
                loc = a.get("lokation", a.get("area", ""))
                if loc and str(loc).strip():
                    unique_areas.add(str(loc).strip())
            true_areas = len(unique_areas)
            most_overdue = max((a.get("days_overdue", 0) for a in delayed_list), default=0)

            if "insight_data" in parsed_json:
                ins = parsed_json["insight_data"]
                ins["delayed_count"] = true_delayed
                ins["critical_count"] = true_critical
                ins["important_count"] = true_important
                ins["monitor_count"] = true_monitor
                ins["root_cause_count"] = true_root_cause_count
                ins["forceable_count"] = forceable
                ins["not_forceable_count"] = not_forceable
                ins["areas_affected"] = true_areas if true_areas > 0 else ins.get("areas_affected", 0)
                ins["most_overdue_days"] = most_overdue

                if true_delayed > 15 or most_overdue > 60:
                    ins["project_status"] = "CRITICAL"
                    ins["risk_level"] = "HIGH"
                elif true_delayed >= 5 or most_overdue > 30:
                    ins["project_status"] = "AT_RISK"
                    ins["risk_level"] = "MEDIUM"
                else:
                    ins["project_status"] = "STABLE"
                    ins["risk_level"] = "LOW"

                import re as _re
                findings = ins.get("critical_findings", [])
                if findings:
                    corrected = []
                    for f in findings:
                        f = _re.sub(r'\b\d+\s+delayed\s+activit', f'{true_delayed} delayed activit', f, flags=_re.IGNORECASE)
                        f = _re.sub(r'\b\d+\s+forsinkede\s+aktivit', f'{true_delayed} forsinkede aktivit', f, flags=_re.IGNORECASE)
                        f = _re.sub(r'\b\d+\s+delayed,', f'{true_delayed} delayed,', f, flags=_re.IGNORECASE)
                        f = _re.sub(r'\b\d+\s+critical\s+root\s+cause', f'{true_root_cause_count} critical root cause', f, flags=_re.IGNORECASE)
                        f = _re.sub(r'\b\d+\s+root\s+cause', f'{true_root_cause_count} root cause', f, flags=_re.IGNORECASE)
                        f = _re.sub(r'\b\d+\s+grundårsag', f'{true_root_cause_count} grundårsag', f, flags=_re.IGNORECASE)
                        f = _re.sub(r'\bonly\s+\d+\s+production', f'only {sum(1 for a in delayed_list if a.get("task_type") == "Production")} production', f, flags=_re.IGNORECASE)
                        corrected.append(f)
                    ins["critical_findings"] = corrected
                    logger.info(f"  [PredictiveAgent] Post-validation: corrected critical_findings numbers")

                mc = parsed_json.get("management_conclusion", "")
                if mc:
                    mc = _re.sub(r'\b\d+\s+delayed\s+activit', f'{true_delayed} delayed activit', mc, flags=_re.IGNORECASE)
                    mc = _re.sub(r'\b\d+\s+forsinkede\s+aktivit', f'{true_delayed} forsinkede aktivit', mc, flags=_re.IGNORECASE)
                    mc = _re.sub(r'\b\d+\s+root\s+cause', f'{true_root_cause_count} root cause', mc, flags=_re.IGNORECASE)
                    parsed_json["management_conclusion"] = mc

            if "schedule_overview" in parsed_json:
                parsed_json["schedule_overview"]["delayed_count"] = true_delayed

            forcing_count = len(fa_final)
            logger.info(f"  [PredictiveAgent] JSON response: {true_delayed} delayed activities, {true_root_cause_count} root causes, model: {model_used}{usage_info}")
            logger.info(f"  [PredictiveAgent] Forcing assessment: {forcing_count} evaluated — {forceable} forceable, {not_forceable} not recommended")

            delayed_ids = [a.get("id", "?") for a in parsed_json.get("delayed_activities", [])]
            logger.info(f"  [PredictiveAgent] Delayed activity IDs: {delayed_ids}")

            # TL-5.6 (brief §31, §45): tag every output element with its
            # `EvidenceClass`. Runs after the post-validation correction
            # block above so the classification reflects the final shape
            # the user actually sees, not the LLM's raw output. Same map
            # the NUSF path's `_merge_narrative_into_facts` produces — both
            # paths converge on the same classification discipline.
            parsed_json["_classification"] = _build_classification(parsed_json)

            # TL-6.1 (brief §33, §34): wrap the response in the agent
            # response contract and run it through the render gate. Additive
            # — `predictive_json`/`predictive_insights` are unchanged for
            # existing callers (`format_predictive_as_html` etc.); this adds
            # a parallel, gated view for callers ready to use it.
            agent_response = validate_agent_response(
                _build_agent_response(parsed_json, user_query=user_query, language=language), policy=GatePolicy.QUALIFY, language=language,
            )

            return {
                "predictive_insights": raw_content,
                "predictive_json": parsed_json,
                "agent_response": agent_response,
                "model": self.deployment,
                "status": "success",
                "raw_llm_response": raw_content,
                "reasoning_content": None,
                "usage_info": ", ".join(usage_parts) if usage_parts else None,
                "system_prompt": system_prompt,
                "user_message": user_message,
                "versions": {
                    "parser": "nusf-pipeline-v2.1" if data_format == "nusf" else "raw-parser-v1.0",
                    "matching_algorithm": "nusf-matcher-v3.2",
                    "analysis_engine": PREDICTIVE_ENGINE_VERSION,
                    "prompt": PREDICTIVE_PROMPT_VERSION,
                    "model": model_used,
                    "schedule_revision": schedule_filename or "rev:current",
                    "manual_corrections": "corrections:none",
                },
            }

        except Exception as e:
            logger.error(f"  [PredictiveAgent] Error: {e}")
            return {
                "predictive_insights": None,
                "predictive_json": None,
                "model": self.deployment,
                "status": "error",
                "error": str(e)
            }

    def analyze_from_facts(
        self,
        structured_context: dict,
        response_facts: dict,
        user_query: str,
        language: str = "en",
        schedule_filename: str = None,
        reference_date: str = None,
    ) -> dict:
        """TL-5.4: the interpretation-only entry point (brief §4, §17).

        Unlike `analyze()`, this never asks the model to detect delays, count
        activities, or invent per-activity facts. `structured_context`
        (`src/trust/context.py`'s `build_predictive_context`) is the ONLY
        schedule data the model sees — it is orders of magnitude smaller than
        the raw text `analyze()` sends, and every fact in it already carries
        a trust signal (brief §17). `response_facts`
        (`build_response_facts`) never goes to the model at all; it is
        merged into the model's narrative response afterward by
        `_merge_narrative_into_facts`, which also enforces that no id absent
        from `structured_context` survives into the final response.

        No post-hoc correction block follows the API call here (contrast
        `analyze()`'s TL-5.2-superseded block) — there is nothing to correct.
        The facts merged in are already correct by construction; the only
        thing this method's response can get wrong is narrative prose, which
        is Phase 6's (`TL-6.3`) job to verify, not this method's to patch.
        """
        logger.info(f"  [PredictiveAgent] Starting narrative-only analysis with {self.deployment} (facts supplied, not requested)...")

        lang_instruction = PREDICTIVE_NARRATIVE_LANGUAGE_INSTRUCTIONS.get(
            language, PREDICTIVE_NARRATIVE_LANGUAGE_INSTRUCTIONS["en"]
        )
        system_prompt = f"{PREDICTIVE_NARRATIVE_SYSTEM_PROMPT}\n\n{lang_instruction}"

        schedule_label = schedule_filename if schedule_filename else "Schedule"

        cet = timezone(timedelta(hours=1))
        today = datetime.now(cet).date()
        da_days = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
        en_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        da_months = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november", "december"]
        en_months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        if language == "da":
            today_str = f"{da_days[today.weekday()]} d. {today.day}. {da_months[today.month - 1]} {today.year}"
        else:
            today_str = f"{en_days[today.weekday()]}, {en_months[today.month - 1]} {today.day}, {today.year}"

        ref_date_instruction = ""
        if reference_date:
            ref_date_instruction = f"\nThe structured context's `reference_date` field ({structured_context.get('reference_date')}) is authoritative — do not use any other date.\n"

        context_json = json.dumps(structured_context, ensure_ascii=False, indent=2)

        user_message = f"""{user_query}

TODAY'S DATE: {today_str}
Use this to set concrete deadlines in executive_actions (real day names and dates).

Schedule filename: "{schedule_label}"
{ref_date_instruction}
═══════════════════════════════════════════════════════════
STRUCTURED, VERIFIED CONTEXT (this is the ONLY schedule data you have — do not ask for more, do not assume more exists):
═══════════════════════════════════════════════════════════
{context_json}
═══════════════════════════════════════════════════════════

Return complete JSON matching the strict schema. Every id you write must come from the context above."""

        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        logger.info(f"  [PredictiveAgent] Narrative LLM input ready (system={len(system_prompt)} chars, context={len(context_json)} chars)")

        try:
            api_params = {
                "model": self.deployment,
                "messages": messages,
                "temperature": 0,
                "top_p": 0.1,
                "seed": 42,
                "max_tokens": 8192,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": NOVA_NARRATIVE_SCHEMA,
                },
            }

            response = self.client.chat.completions.create(**api_params)
            choice = response.choices[0]
            raw_content = choice.message.content or ""

            if not raw_content and hasattr(choice.message, "refusal") and choice.message.refusal:
                logger.warning(f"  [PredictiveAgent] Model refused: {choice.message.refusal}")
                return {"predictive_insights": None, "predictive_json": None, "model": self.deployment, "status": "error", "error": f"Model refused: {choice.message.refusal}"}

            if not raw_content:
                logger.warning(f"  [PredictiveAgent] Empty content. finish_reason={choice.finish_reason}")
                return {"predictive_insights": None, "predictive_json": None, "model": self.deployment, "status": "error", "error": "Empty response from model"}

            try:
                narrative = json.loads(raw_content)
            except json.JSONDecodeError as je:
                logger.error(f"  [PredictiveAgent] Narrative JSON parse error: {je}")
                return {"predictive_insights": raw_content, "predictive_json": None, "model": self.deployment, "status": "error", "error": f"Invalid JSON: {je}"}

            parsed_json = _merge_narrative_into_facts(response_facts, structured_context, narrative)

            usage = getattr(response, "usage", None)
            usage_parts = []
            if usage:
                usage_parts.append(f"prompt={usage.prompt_tokens}")
                usage_parts.append(f"completion={usage.completion_tokens}")

            logger.info(
                f"  [PredictiveAgent] Narrative response merged: "
                f"{len(parsed_json['delayed_activities'])} delayed activities (facts), "
                f"{len(parsed_json['forcing_assessment'])} forcing assessments (narrative), model: {self.deployment}"
            )

            # TL-6.1 (brief §33, §34): same gate as `analyze()` — additive,
            # `predictive_json` is unchanged for existing callers.
            agent_response = validate_agent_response(
                _build_agent_response(parsed_json, user_query=user_query, language=language), policy=GatePolicy.QUALIFY, language=language,
            )

            return {
                "predictive_insights": raw_content,
                "predictive_json": parsed_json,
                "agent_response": agent_response,
                "model": self.deployment,
                "status": "success",
                "raw_llm_response": raw_content,
                "reasoning_content": None,
                "usage_info": ", ".join(usage_parts) if usage_parts else None,
                "system_prompt": system_prompt,
                "user_message": user_message,
            }

        except Exception as e:
            logger.error(f"  [PredictiveAgent] Error: {e}")
            return {
                "predictive_insights": None,
                "predictive_json": None,
                "model": self.deployment,
                "status": "error",
                "error": str(e),
            }


predictive_agent = PredictiveAgent()
