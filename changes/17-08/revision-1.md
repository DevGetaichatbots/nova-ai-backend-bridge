Hi guys,

Great work on this update. 🙏
You have understood Andreas’ feedback correctly, and this is a big improvement compared to the previous Changed Activities table.

I especially like:

The new Change chips showing exactly what changed.
The expandable rows showing old value → new value → difference.
The filters for Start, Finish, Duration, Progress, ID and Multiple.
The Largest Impact sorting.
Keeping unchanged information visually neutral.
The new “Unable to verify change” behaviour instead of guessing when data is uncertain.

This is exactly the direction we want for Nova:

Don’t just show the user data — explain the data so they understand it immediately.

There are, however, a few important things I want us to adjust before we consider this finished.

1. Please verify the Duration values — IMPORTANT

In the screenshot I can see values such as:

Duration +10,056d (27 years)
Duration +9,580d
Duration +8,904d
Duration +8,448d

These numbers look extremely unusual.

Before changing anything, please check the original source schedules/PDFs and determine exactly why Nova is producing these values.

It may be a unit issue, parsing issue, conversion issue, or the source may genuinely contain values that are being interpreted differently.

Do not assume what the problem is. Verify it against the source.

This is especially important because we are making trust and data reliability one of Nova’s core principles. If Andreas or Emil sees “+10,056 days” and it is incorrect, they will immediately question the rest of the analysis.

If Nova cannot reliably determine the duration/unit, it is better to show:

Unable to verify

than to confidently display a potentially incorrect number.

2. Make the change labels more human-readable

Currently we have things like:

↑ Start -83d
↑ Finish +336d

Technically this communicates the difference, but the combination of arrows and +/- requires the user to interpret what it means.

I would prefer:

Start · 83 days earlier
Finish · 336 days later
Duration · 12 days longer
Progress · 14 pp lower

In the Danish K&L version:

Start · 83 dage tidligere
Slut · 336 dage senere
Varighed · 12 dage længere
Fremdrift · 14 pp lavere

The goal is that Andreas can understand every change instantly without mentally calculating what + / - / ↑ / ↓ means.

3. Be careful with “IMPROVEMENT”

In the expanded example, a start date moving 83 days earlier is labelled:

FORBEDRING / IMPROVEMENT

We should not automatically call this an improvement.

Nova knows that:

The activity moved 83 days earlier.

But that does not necessarily mean it is better for the project. It could simply be a schedule change or resequencing.

This connects directly to the Trust Layer we are building:

Nova should communicate facts confidently, but should never interpret something as positive/negative unless we have sufficient evidence to support that conclusion.

So for Changed Activities, please prioritize factual language:

83 days earlier
336 days later

rather than automatically:

Improvement / Delay

We can still use visual indicators where the meaning is objectively clear, but we should be careful about making unsupported conclusions.

4. Keep the current simplicity

Please do not solve these changes by adding lots of additional columns or information.

The new design is good because it is much easier to scan.

Keep the principle:

WHAT changed → FROM what → TO what → BY how much

Overview = extremely simple.

Expand row = detailed explanation.

This is exactly what we want.

5. Trust is more important than completeness

Going forward, please keep this principle in mind throughout Nova:

If Nova knows → show it clearly.
If Nova is uncertain → flag it.
If Nova cannot verify → say so.
Never guess just to provide an answer.

This is especially important for IDs, dates, durations, progress and activity matching.

Overall, very good work guys. 👏

You absolutely understood the main UX problem Andreas identified, and the new table is significantly better and much closer to how I want Nova to communicate project data.

So please keep the overall design and functionality. I am not asking for a redesign.

We mainly need to:

1. Verify/fix the suspicious Duration values against the source.
2. Make earlier/later changes easier to understand.
3. Avoid calling something an improvement unless Nova can actually prove that interpretation.
4. Keep the “Unable to verify” behaviour whenever the data is uncertain.

Once these are addressed and tested against several different schedule comparisons, I think this will be a really strong improvement for Andreas, Emil and future users.

Great job on this update. 🙏🔥