from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam
from src.config import settings
from typing import List
from datetime import datetime, date, timezone, timedelta
import json
import logging

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
                        "description": "One concrete sentence starting with 'If no action is taken, ...' — state the expected total delay window and the primary cause. Example: 'If no action is taken, your project is expected to be delayed by 4–8 months due to unresolved coordination and design dependencies.'"
                    },
                    "estimated_delay_impact": {
                        "type": "string",
                        "description": "Concise delay estimate derived from most_overdue_days and cascade risk. Format: '+N weeks' or '+N–M months'. Examples: '+6 weeks', '+3–5 months', '+8–12 weeks'. NEVER vague — always give a number range."
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

- **what_will_happen**: Write exactly ONE sentence starting with "If no action is taken, ...". State the expected delay window (in weeks or months) AND the primary cause category. Use the most_overdue_days to derive the window: <30 days → "+2–4 weeks", 30–60 days → "+4–8 weeks", 60–90 days → "+2–3 months", 90–180 days → "+3–6 months", >180 days → "+6–12 months or more". Adjust upward if there are cascading root causes across multiple disciplines. NEVER write "significant delay" or "some delay" — always give a number range.

- **estimated_delay_impact**: Short form of the delay window only. Format "+N weeks" or "+N–M months". Derived from the same logic as what_will_happen.

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
        reference_date: str = None
    ) -> dict:
        logger.info(f"  [PredictiveAgent] Starting analysis with {self.deployment} (strict JSON schema)...")

        lang_instruction = PREDICTIVE_LANGUAGE_INSTRUCTIONS.get(
            language, PREDICTIVE_LANGUAGE_INSTRUCTIONS["en"]
        )
        system_prompt = f"{PREDICTIVE_SYSTEM_PROMPT}\n\n{lang_instruction}"

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
- Only skip grouping/summary headers (e.g. section headers like "Omr. 1", "E100.XX", "Globals", "Afhængigheder", "Færdiggøre projektering").

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

            return {
                "predictive_insights": raw_content,
                "predictive_json": parsed_json,
                "model": self.deployment,
                "status": "success",
                "raw_llm_response": raw_content,
                "reasoning_content": None,
                "usage_info": ", ".join(usage_parts) if usage_parts else None,
                "system_prompt": system_prompt,
                "user_message": user_message
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


predictive_agent = PredictiveAgent()
