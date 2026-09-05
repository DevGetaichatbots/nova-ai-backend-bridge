Hi guys,

We got very useful feedback from Andreas at K&L today after he tested the upload/comparison himself.

He uploaded two schedules and Nova correctly identified the changed activities, but his question was essentially:

“Can Nova clearly mark what exactly has changed?”

This is important and directly relates to what we have discussed about data communication and making Nova immediately understandable.

Right now, Nova tells the user that an activity has changed, but the user still has to scan across OLD START / NEW START / OLD FINISH / NEW FINISH / DURATION / PROGRESS etc. and manually figure out what changed.

We need to remove that work from the user.

What I want us to build

For every activity in Changed Activities, Nova should automatically identify the exact fields that changed and communicate the change clearly.

For example:

Start Date: 01-05-2026 → 13-05-2026 (+12 days)
Finish Date: 20-05-2026 → 07-06-2026 (+18 days)
Duration: 20 → 17 days (-3 days)
Progress: 44% → 30% (-14 pp)

Instead of the current CHANGE column simply saying:

Start Date
Finish Date
Progress

it should communicate the actual result, for example:

Start +12d
Finish +18dma
Progress -14pp

If multiple fields changed, show all relevant changes clearly.

Visual highlighting

We should also visually highlight only the values that actually changed.

The user should be able to look at one row for 1–2 seconds and immediately understand:

1. WHAT changed?
2. FROM what?
3. TO what?
4. BY how much?
5. Was the change positive or negative?

Example:

Finish Date 20-05-2026 → 07-06-2026 +18 days

A delay/worsening should be visually clear, while an improvement should also be visually distinguishable.

Unchanged values should remain visually neutral and should not compete for attention.

Important: do not infer anything

This must be based entirely on the parsed and verified values from the two schedules.

We are currently making trust and reliability a top priority, so Nova must never invent a change or calculate from uncertain/missing values as if they were confirmed.

If either OLD or NEW value cannot be reliably extracted/verified, show something like:

“Unable to verify change”

rather than guessing.

This should later connect directly to the Confidence / Verification Layer we are building.

Ideally also add sorting/filtering

It would be very useful if the user can quickly filter Changed Activities by:

Start date changed
Finish date changed
Duration changed
Progress changed
ID changed
Multiple changes

And ideally sort by largest impact/change, so the most significant changes appear first rather than forcing the project manager to scroll through hundreds of activities.

UX principle

Please keep this VERY SIMPLE.

Andreas and Emil should not need to understand how Nova works internally.

The goal is:

Nova finds the data → Nova identifies the change → Nova explains the change → the user understands it instantly.

We should not just give them a database/table of information and expect them to interpret it themselves.


Nova should prioritize and communicate the data, not just display it.

