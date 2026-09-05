NOVA INSIGHT
TRUST, CONFIDENCE & VERIFICATION LAYER
Technical & Product Implementation Specification

Priority: CRITICAL / NEXT DEVELOPMENT MILESTONE

1. PROJECT OBJECTIVE

Nova Insight must become a system that project managers can trust in daily operational use.

The fundamental principle is:

Nova must never pretend to know something it does not know.

A missing answer is acceptable.

An uncertain answer clearly marked as uncertain is acceptable.

A confidently presented incorrect answer is not acceptable.

Nova must therefore be designed around:

Verified truth > plausible answer

This applies to every layer of the system:

Source PDF → OCR → Parsing → Activity Identification → Schedule Matching → Calculations → Analysis → AI Interpretation → Dashboard → Reports

The objective is not to claim that Nova is “100% accurate”.

The objective is to make Nova transparent about what it knows, what it inferred, and what it cannot verify.

2. THE CORE PRODUCT PRINCIPLE

Nova should have three possible responses to information:

1. VERIFIED

Nova has sufficient evidence to present the information normally.

2. UNCERTAIN

Nova has some evidence, but cannot verify the result with sufficient confidence.

The user must be informed.

3. UNKNOWN / UNVERIFIED

Nova cannot reliably determine the answer.

Nova must not guess.

Instead:

Unable to verify from source data.

This principle must apply throughout the platform.

3. BUILD A NOVA TRUST ENGINE

Do not treat confidence as only an OCR feature.

Create a centralized:

Nova Trust Engine

Every important output should have an internal provenance and confidence state.

Conceptually:

SOURCE DOCUMENT
      ↓
OCR CONFIDENCE
      ↓
PARSING CONFIDENCE
      ↓
IDENTITY CONFIDENCE
      ↓
MATCH CONFIDENCE
      ↓
CALCULATION VALIDATION
      ↓
ANALYSIS CONFIDENCE
      ↓
AI CLAIM VERIFICATION
      ↓
USER OUTPUT

A high-confidence AI response cannot override weak upstream data.

Confidence must propagate through the pipeline.

4. CRITICAL ARCHITECTURE RULE
The LLM must NOT be the source of truth.

This is probably the single most important technical requirement.

The AI/LLM should not independently “look at the schedule and decide” numerical facts whenever those facts can be determined programmatically.

Separate Nova into two layers:

DETERMINISTIC DATA LAYER

Responsible for facts:

Activity ID
Activity Name
Start Date
Finish Date
Duration
Progress
Location
Trade
Building
Floor
Phase
schedule revision
calculated changes
matching
counts
delays
progress deviations

These values should come from:

OCR + parsing + validated calculations/database queries.

AI INTERPRETATION LAYER

Responsible for explaining validated facts:

“31 delayed activities are concentrated in Building NK.”

But the LLM should not invent the number 31.

The system calculates:

delayed_activities_NK = 31

and provides that validated value to the LLM.

The LLM's job becomes:

explain the truth

rather than:

discover/invent the truth.

5. SOURCE PROVENANCE

Every important value stored by Nova should retain information about where it came from.

For example:

Activity:
EL – Cable Tray Installation


Activity ID:
A-1427


Source:
Schedule Revision 07


PDF Page:
14


OCR Confidence:
98.4%


Parser Confidence:
100%


Match Method:
Exact Activity ID


Match Confidence:
100%

This information does not necessarily need to be visible constantly.

But Nova should know it.

That gives us data lineage.

If something goes wrong, we can trace:

Where did this number come from?

6. OCR CONFIDENCE LAYER

You already discussed this.

Now make it systematic.

For every OCR-extracted critical field, store:

raw_value
normalized_value
ocr_confidence
page_number
bounding_box
source_document

Critical fields include especially:

Activity ID
Activity Name
Start Date
Finish Date
Duration
Progress

Potentially also:

Trade
Location
Building
Floor
Phase

depending on schedule structure.

7. OCR CONFIDENCE THRESHOLDS

Do NOT hard-code arbitrary thresholds without calibration against real K&L schedules.

But structurally support something like:

GREEN — HIGH CONFIDENCE

Example:

≥ 95%

Normal processing.

AMBER — REVIEW

Example:

80–94.9%

Nova may process the value but should flag it internally and, where material, visually.

RED — UNVERIFIED

Example:

<80%

Nova should not treat the value as reliable fact without secondary verification.

Important: these numbers are starting hypotheses, not final thresholds.

Run them against a validation dataset first.

8. FIELD IMPORTANCE MUST MATTER

A 90% confidence score on:

“description”

is not necessarily equivalent to 90% confidence on:

Activity ID

Some fields are structurally critical.

Define:

CRITICAL FIELDS

Activity ID
Activity Name
Start/Finish
Progress

Errors can materially change analysis.

SECONDARY FIELDS

Descriptions
Notes
metadata etc.

Critical fields should have stricter validation requirements.

9. THE ID PROBLEM

This is particularly important because of the current discussion with Andreas/K&L.

Current logic is approximately:

Azure OCR processes image-based PDFs.

Nova searches for a stable identifier existing across old and new schedules.

If a reliable identifier cannot be found, Nova currently falls back to:

Activity Name + Location

This is sensible as a matching strategy.

But we need to separate:

MATCHING IDENTITY

from:

SOURCE ACTIVITY ID

They are NOT necessarily the same thing.

10. NEVER INVENT AN ACTIVITY ID

Absolute rule:

Nova must never generate, infer or hallucinate a source Activity ID.

If OCR cannot reliably read an ID:

Display:

ID: Unable to verify

or

ID: —

with appropriate status.

Never:

A-124

because it “looks likely”.

This should be impossible at architecture level, not merely discouraged in the prompt.

11. PRESERVE BOTH SOURCE IDs

Suppose:

OLD SCHEDULE
ID: A142
Activity:
Electrical installation


Location:
Building NK
NEW SCHEDULE
ID: A198
Activity:
Electrical installation


Location:
Building NK

Nova may determine that these represent the same activity through other evidence.

The dashboard should retain:

Previous ID: A142

Current ID: A198

and potentially:

⚠ ID changed

Do not silently replace one with the other.

12. MATCH CONFIDENCE

Every comparison between activities should receive a Match Confidence.

Possible matching hierarchy:

LEVEL 1 — EXACT VERIFIED ID

Same verified source identifier.

Very high confidence

LEVEL 2 — STRONG MULTI-FIELD MATCH

Example:

Activity Name

Location
Trade
Building/Floor

all align.

High confidence

LEVEL 3 — PARTIAL MATCH

Activity Name + Location align but other information differs/missing.

Medium confidence

LEVEL 4 — PROBABLE/FUZZY MATCH

Similarity exists but insufficient evidence.

Low confidence

LEVEL 5 — NO RELIABLE MATCH

Nova must not match.

Activity should instead be categorized appropriately as:

Potentially added

Potentially removed

or:

Requires verification

depending on evidence.

13. DO NOT FORCE MATCHES

This deserves its own rule.

If Nova has:

Old schedule activity:
Install ventilation ducts – Floor 2


New schedule possibilities:


Install ventilation – Floor 2
Install ventilation ducts – Floor 3
Install main ventilation – Floor 2

and cannot confidently determine which is the corresponding activity:

DO NOT PICK ONE.

Return:

Match requires verification

This prevents one uncertain match from contaminating every downstream calculation.

14. CONFIDENCE PROPAGATION

This is where the system becomes genuinely robust.

Suppose:

OCR ID Confidence = 99%
Parsing Confidence = 100%
Match Confidence = 96%
Calculation Validation = 100%

The output can reasonably be High Confidence.

But:

OCR ID Confidence = 67%
Parsing Confidence = 91%
Match Confidence = 58%

The final analysis must NOT suddenly become:

98% confident

because an LLM thinks the answer sounds plausible.

Upstream uncertainty must propagate downstream.

The Trust Engine should calculate a final state based on the weakest materially relevant dependency.

Not necessarily a simple average.

For critical dependencies, use a weakest-link / rule-based model.

15. CALCULATIONS MUST BE DETERMINISTIC

Anything that can be mathematically calculated should NOT be calculated by the LLM.

Example:

Old progress:

68%

New progress:

24%

Deviation:

24 - 68 = -44 percentage points

That calculation should happen in code.

Not in GPT.

Same for:

counts
durations
date differences
number of delayed activities
number of critical activities
percentage distributions
revision changes

The LLM receives the calculated results.

16. CLAIM-LEVEL VERIFICATION

This is one of the biggest improvements I would build.

Before an AI-generated explanation reaches the user, break it into factual claims.

Example AI output:

“Electrical works in Building NK are the project's largest concentration of delay, with 17 activities behind schedule and three critical activities.”

Nova should verify:

Claim 1:
Electrical works are largest concentration.
→ DATABASE CHECK


Claim 2:
17 activities delayed.
→ DATABASE COUNT


Claim 3:
3 are critical.
→ DATABASE COUNT

Only after validation should the statement be displayed.

If claim 3 cannot be validated:

Nova must either remove it or say:

“Critical status could not be verified for all activities.”

17. STRUCTURED AI INPUTS

Do not send huge raw OCR dumps to the LLM and ask:

“What is happening?”

Instead generate structured verified context.

For example:

{
  "project_status": {
    "delayed_activities": 73,
    "critical_delayed": 6
  },
  "clusters": [
    {
      "location": "NK",
      "trade": "EL",
      "delayed": 17,
      "critical": 3,
      "confidence": "high"
    }
  ]
}

Then tell the AI:

Explain only the supplied facts. Do not introduce facts not contained in the structured context.

That dramatically reduces hallucination surface.

18. NO-ANSWER BEHAVIOUR

The agent must explicitly be trained and technically allowed to say:

“I cannot verify that from the uploaded schedules.”

This is a feature, not a failure.

Examples:

User:

“Why is Activity A142 delayed?”

Nova knows only that it is delayed.

Nova does NOT know why.

Wrong:

“The delay appears to be caused by dependencies from electrical installation.”

unless source data proves this.

Correct:

“The schedule shows Activity A142 is delayed by 18 days, but the uploaded data does not contain enough information to determine the cause.”

Potential follow-up:

“I can show you the predecessor activities and recent schedule changes that may help identify the cause.”

That answer creates trust.

19. DISTINGUISH FACT FROM INFERENCE

Nova should internally classify statements as:

FACT

Directly supported by source/calculation.

Example:

“Finish date moved by 18 days.”

DERIVED FACT

Deterministically calculated.

Example:

“31 of 73 delayed activities are located in NK.”

INFERENCE

Evidence suggests something but does not prove it.

Example:

“The concentration of delays around electrical works may indicate a coordination bottleneck.”

UNKNOWN

Insufficient evidence.

Never present inference as fact.

20. LANGUAGE MATTERS

Avoid:

“The project will be delayed.”

unless Nova genuinely has sufficient predictive evidence and the prediction is clearly represented as probabilistic.

Prefer:

“The current schedule pattern indicates increased delay risk.”

Likewise:

Wrong:

“Electrical work caused the delay.”

Better:

“The largest concentration of current delay is within electrical activities.”

unless causality has actually been established.

This is extremely important for construction professionals.

21. USER-FACING CONFIDENCE DESIGN

Do NOT turn Nova into a Christmas tree with green/yellow/red icons everywhere.

Confidence should be available without overwhelming the user.

I recommend three visible states:

● VERIFIED

Green indicator.

Tooltip:

Verified against source schedule.

● REVIEW

Amber.

Tooltip:

Nova identified uncertainty in the source data or activity match. Review recommended.

● UNVERIFIED

Red/neutral warning.

Tooltip:

Nova could not reliably verify this value. It has not been used as confirmed data.

22. PROJECT-LEVEL TRUST INDICATOR

At the top of the dashboard add something like:

DATA CONFIDENCE
96% VERIFIED

Then:

1,187 / 1,236 activities verified

31 require review

18 could not be reliably matched

This is enormously valuable.

Instead of K&L wondering:

“Can we trust this dashboard?”

Nova tells them:

Here is exactly how much of this dashboard we can verify.

23. DO NOT CALL EVERYTHING “96% ACCURATE”

Important distinction:

Confidence ≠ accuracy.

If Azure reports 96% OCR confidence, that does NOT prove the value is correct 96% of the time.

Therefore user-facing language should preferably be:

Verified / Review / Unverified

rather than making mathematically unsupported claims like:

“Nova is 98.7% accurate.”

Any percentage displayed to users must have a precisely defined denominator and calculation.

For example:

96% of activities passed Nova's verification rules

is defensible.

24. CLICK INTO THE EVIDENCE

This could become one of Nova's strongest trust features.

When a user clicks an activity:

NOVA
Activity
EL – Cable Tray Installation


Current ID
A142


Previous ID
A142


Status
Behind schedule


Deviation
-44 pp


Match
Verified

Then:

SOURCE VERIFICATION
Old Schedule
Page 14


New Schedule
Page 16


Match Method
Exact Activity ID


Data Status
Verified

Potentially allow:

View source

which takes the user directly to/highlights the relevant row in the source schedule/PDF.

Now the user doesn't have to trust Nova blindly.

They can audit Nova.

That is extremely powerful.

25. HUMAN REVIEW QUEUE

Create:

REVIEW REQUIRED

Example:

31 items require review

Categories:

12 low-confidence IDs

8 uncertain activity matches

6 unreadable dates

5 conflicting values

Users can resolve them.

Example:

Nova found two possible matches for Activity “Ventilation Level 2”.

Option A
Option B
No match

The user's decision becomes authoritative for that comparison.

26. MANUAL CORRECTIONS MUST NOT DISAPPEAR

If Andreas corrects:

Activity X in Revision 1 = Activity Y in Revision 2

Nova should store the resolution for the project where appropriate.

Do not make him correct the same deterministic ambiguity every upload if the relevant identity relationship remains valid.

Create a:

VERIFIED MATCH MAPPING

But mappings must be versioned and invalidated when underlying evidence changes materially.

27. CONFLICT DETECTION

Nova should actively search for contradictions.

Examples:

Same ID → different activity names.

Same activity → multiple IDs.

Finish date before start date.

Progress >100%.

Missing duration.

Duplicate activity IDs.

Impossible date parsing.

Activity marked removed but appears elsewhere.

Large unexplained field changes.

Instead of silently resolving:

FLAG THEM.

Example:

⚠ Source conflict detected

Activity ID A142 appears against two different activity names.

28. SOURCE QUALITY CHECK BEFORE ANALYSIS

Before Nova analyzes a schedule, perform a:

PRE-FLIGHT CHECK

Example:

Schedule Quality

Good

1,236 activities detected
1,204 confidently parsed
19 require review
13 unresolved

Then:

Analysis can proceed.

Or:

Schedule Quality

Insufficient

Large sections of the PDF could not be reliably parsed.

Nova has paused analysis to avoid producing unreliable results.

That is exactly the behaviour K&L should learn to trust.

29. ANALYSIS GATING

Not every bad field should stop the entire project.

Use three levels:

PASS

Analysis continues normally.

PARTIAL

Analysis continues, but affected activities/features are excluded or marked.

BLOCK

The required source quality is too poor to safely perform the requested analysis.

Example:

If 10 IDs are unreadable but strong alternative matches exist:

PARTIAL

If half the schedule cannot be parsed:

BLOCK

30. CONFIDENCE MUST BE FEATURE-SPECIFIC

A project should not simply have one generic confidence number.

Nova might have:

Schedule Parsing       VERIFIED
Activity Matching      VERIFIED
Progress Comparison    VERIFIED
Critical Path          REVIEW
Forecast                UNAVAILABLE

Therefore:

“Nova trusts the project 93%”

is less useful than telling users which analyses are trustworthy.

31. PREDICTIVE FEATURES REQUIRE EVEN HIGHER STANDARDS

This becomes critical when Nova Predictive launches.

Nova must clearly distinguish:

HISTORICAL FACT

Activity moved 14 days.

from

FORECAST

Nova estimates elevated risk of a further delay.

Forecasts should show:

Prediction

Confidence band/category

Evidence

Key drivers

and ideally:

Why Nova thinks this

Never make a prediction visually indistinguishable from an observed fact.

32. “WHY?” BUTTON

Every major Nova recommendation should support:

WHY?

Example:

HIGH RISK — Electrical / NK / Floor 2

Click:

Why Nova flagged this
11 activities currently delayed
3 are critical
7 worsened since previous revision
average finish movement: +18 days
4 downstream dependencies affected
Confidence

HIGH

Evidence

22 verified schedule records

Now Nova becomes explainable rather than magical.

33. AGENT RESPONSE CONTRACT

Developers should implement a strict response contract.

Every agent answer should internally contain something equivalent to:

answer
supporting_facts[]
source_references[]
confidence_state
inferences[]
unverified_claims[]

Before rendering:

IF unverified_claims > 0:
    remove / qualify / reject claims

The frontend does not necessarily expose this raw structure.

But the backend should enforce it.

34. SYSTEM PROMPT RULES ARE NOT ENOUGH

Do NOT solve this only by writing:

“Do not hallucinate.”

inside the system prompt.

LLMs can still make mistakes.

Reliability must be enforced through:

architecture + structured data + validation + provenance + deterministic calculations + confidence gating + prompts.

Prompt engineering is the last layer, not the safety architecture.

35. TESTING — BUILD A GOLDEN DATASET

Before K&L relies on Nova daily, build a controlled benchmark.

Take real anonymized schedules and manually establish the correct ground truth.

Example:

GOLDEN DATASET

10–20 schedule pairs initially.

Then hundreds/thousands of known activities.

For each:

Correct ID
Correct activity name
Correct dates
Correct progress
Correct match
Correct status
Correct changes

Run every Nova release against this dataset.

36. AUTOMATED REGRESSION TESTING

Every deployment should answer:

Did parsing improve or deteriorate?

Did matching improve?

Did a new parser break existing schedules?

Did ID accuracy decline?

Did previously verified activities become uncertain?

Set release gates.

Example:

Critical-field extraction regression:
NOT ALLOWED


False-match regression:
NOT ALLOWED


Known calculation regression:
NOT ALLOWED

A shiny new feature must not silently reduce reliability.

37. MEASURE FALSE POSITIVES SEPARATELY

This is crucial.

For Nova, an incorrect confident match can be worse than no match.

Therefore optimize for:

PRECISION FIRST.

I'd rather Nova correctly match 95 activities and say:

“5 require review”

than match all 100 while 3 are secretly wrong.

For enterprise trust:

Correct + incomplete beats complete + unreliable.
38. TRACK TRUST METRICS

Build internal observability.

Track:

Critical Field Verification Rate

Activity Match Precision

Unmatched Activity Rate

Manual Review Rate

OCR Review Rate

False Match Rate

Conflict Detection Rate

Agent Unsupported Claim Rate

Human Correction Rate

Regression Failure Rate

These should become internal Nova quality KPIs.

39. AGENT UNSUPPORTED CLAIM RATE

This metric deserves special attention.

Run test questions against known schedules.

Measure:

How often does Nova state a factual claim that cannot be traced to verified source data?

Target:

0 unsupported factual claims

That is more strategically valuable than making the agent sound intelligent.

40. AUDIT LOG

For enterprise use, store:

Schedule uploaded
↓
Parser version
↓
OCR provider/version where available
↓
Confidence results
↓
Matches generated
↓
Manual corrections
↓
Analysis version
↓
Agent answer
↓
Evidence used

If K&L asks:

“Why did Nova say this on 12 August?”

you should be able to reconstruct the answer.

41. VERSION EVERYTHING

Store versions for:

parser

matching algorithm

analysis engine

prompt

model

schedule

manual corrections

This becomes extremely important when results change over time.

42. USER EXPERIENCE WHEN NOVA IS UNSURE

This should feel reassuring, not broken.

Bad:

ERROR

Better:

Review required

Nova found insufficient evidence to reliably match this activity between the two schedules.

The activity has therefore been excluded from confirmed comparison results.

Review match →

That communicates:

Nova protected you from a potentially incorrect result.

43. TRUST CENTER

Eventually create a small:

NOVA TRUST CENTER

for enterprise admins.

Show:

Data Verification

98.1% verified

Activity Matching

97.4% verified

Items Requiring Review

23

Unresolved

7

Last Validation

16 Aug 2026

Analysis Engine

vX.X

Potentially:

View verification report

This could become a serious enterprise differentiator.

44. PDF REPORTS MUST CARRY THE SAME TRUST MODEL

Do not make dashboard transparent but PDF reports absolute.

If a report contains uncertain data:

mark it.

Example:

⚠ Based on partially verified activity matching.

And provide methodology/footer information where appropriate.

45. IMPORTANT: DO NOT LET USERS CONFUSE “AI” WITH SOURCE DATA

Nova should visually distinguish:

SOURCE DATA

What the schedule says.

NOVA CALCULATION

What Nova deterministically calculated.

NOVA INSIGHT

What Nova inferred/interpreted.

NOVA FORECAST

What Nova predicts.

This alone could dramatically improve trust.

46. RECOMMENDED USER-FACING TERMINOLOGY

I would standardize on:

Verified

Review Recommended

Unable to Verify

Source Conflict

Nova Insight

Nova Forecast

Avoid vague labels like:

AI thinks

or

Probably correct

Enterprise users need professional language.

47. PRIORITY IMPLEMENTATION PLAN

Do NOT attempt everything simultaneously.

P0 — MUST BUILD NOW

1. Provenance model

Every critical value knows its source.

2. OCR confidence storage

Do not throw confidence metadata away.

3. ID verification

Never invent IDs.

4. Matching confidence

Every match has a state/method.

5. No forced matching

Low confidence → review.

6. Deterministic calculations

Remove LLM calculations wherever possible.

7. Structured agent context

Agent receives verified facts.

8. Strict unknown behaviour

No evidence → no factual answer.

9. User-facing Verified / Review / Unverified

Basic UI.

10. Golden dataset

Start regression testing immediately.

48. P1 — NEXT

Build:

Review Queue

Source Conflict Detection

Source Viewer

Why? explanations

Project Data Quality summary

Feature-specific confidence

audit logging

manual match correction

49. P2 — ENTERPRISE MATURITY

Build:

Trust Center

full lineage explorer

automated validation reports

advanced anomaly detection

predictive calibration

confidence monitoring over time

enterprise audit export

50. DEFINITION OF DONE FOR K&L

I would NOT define completion as:

“The dashboard works.”

Define it as:

A project manager uploads two schedules.

Nova processes them.

Nova knows which activities it can confidently identify.

Nova knows which activities it can confidently match.

Nova isolates ambiguous data.

Nova performs calculations deterministically.

Nova never invents missing IDs.

Nova never silently forces uncertain matches.

Nova explains which results are verified.

Nova clearly flags uncertain results.

Nova can show the source behind important claims.

Nova refuses to answer factual questions where the evidence is insufficient.

Nova's agent cannot present unsupported factual claims as fact.

And a K&L project manager can therefore make the following assumption:

If Nova presents something as VERIFIED, there is traceable evidence behind it. If Nova is uncertain, Nova tells me.

THAT is the product promise.

51. THE PRODUCT PHILOSOPHY I WOULD GIVE THE DEVELOPERS

Put this literally at the top of the Jira epic / development specification:

NOVA DOES NOT NEED TO KNOW EVERYTHING.

NOVA NEEDS TO KNOW WHAT IT KNOWS.

If the source data is reliable, Nova should answer clearly.

If the source data is uncertain, Nova should communicate the uncertainty.

If the answer cannot be verified, Nova must say so.

Never fabricate, silently infer, or force a result simply to provide an answer.

Every important factual claim should ultimately be traceable back to source data or a deterministic calculation.

52. WHY THIS MATTERS COMMERCIALLY

This isn't just backend cleanup.

This can become one of Nova's strongest selling points.

Everyone can put an LLM on top of project data and produce impressive-looking text.

The difficult part is creating an AI system a project director trusts when millions of kroner and months of construction are involved.

Your pitch to K&L eventually becomes:

Nova doesn't ask you to blindly trust AI.

Every critical result is verified against the underlying project data.

When the source is uncertain, Nova tells you.

When Nova cannot verify something, it doesn't invent an answer.

And when you need to understand why Nova reached a conclusion, you can trace it back to the underlying schedule.

That's much stronger than:

“Our AI is really accurate.”

And importantly, don't promise “100% correct” or “3000% trustworthy” externally. The professional promise is:

Transparent. Traceable. Verifiable.

That is what I would make P0 immediately, even before piling more intelligence/features onto Nova. If the foundation isn't trusted, predictive analysis, Project Health and every future module inherit the same trust problem.