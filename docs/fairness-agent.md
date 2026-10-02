# The fair household agent

How Huddle splits household chores, what "fair" means, what stays private, and where the limits are.
The planner is `server/engine/chores.py` (pure logic) and the household service is `server/engine/home.py`.

## What a household member does
1. **Tells the agent privately** how many hours of household work they can take this week (chores, plus any care they've agreed to), what they love, avoid or can't do,
   what they're good at, what they'd like to learn, and anything they know how to do ("plumbing", "the car").
2. **Adds chores any time**, in plain words ("clean the gutters by Saturday, about an hour") or with details. A chore
   can be **pre-planned** (a due date, or a daily, weekly, every-other-week or monthly recurrence) or **ad hoc**.
3. **Gets a plan** each week. The first plan is made deliberately ("Plan the week"); after that the agent plans each
   new week by itself on the scheduler. Ad hoc chores added to a planned week are **offered** to the best-fit person,
   who can accept or decline; a decline (or no answer for 24 hours) means the agent asks the next person.
4. **Marks chores done**, can **hand one back** (the agent asks someone else), and says in private how the week felt.

## What "fair" means here
Fairness is decided in this order, and each step never undoes the one before it:

1. **Hard limits.** Nobody is given a chore in a category they said they can't do. Nobody is given more minutes than
   they offered. A member who is exempt this week gets nothing. As much of the work as possible is covered.
2. **A fair share.** Each person's share of the total *burden* is proportional to their own declared availability.
   - **Burden** is minutes weighted by how heavy the chore is (light 1.0, medium 1.25, heavy 1.5), plus a premium of
     0.25 for **mental load** (planning, booking, remembering, paperwork). Mental load is real work even though it's invisible.
   - **A floor:** the share is never based on less than 40% of the household's mean availability, so claiming almost no
     time doesn't erase your share. You still can't be given more than you said you could take.
   - **A ledger:** over the last 8 weeks, what people actually *did* (marked done) is compared with their fair share. Someone
     who carried extra gets a lighter share now; someone who carried less gets more. Half the gap is carried forward.
   - **How the week felt:** if someone said last week was far too heavy (1) or heavy (2), their share is reduced by 20% or 10%.
   - **Care already taken on counts.** If the household has a closed care plan, each person's share of it is counted
     as work already carried, so someone with heavy care gets fewer chores. It is estimated from what the household
     already sees (who owns each care task and the task's total hours, split evenly when several people own it),
     never from anyone's private hours.
   The planner minimises the *largest* gap between anyone's load and their fair share, then locks in whoever is stuck
   at that gap (for example someone already carrying far more than their share) and keeps minimising among everyone
   else (a leximin), so the rest of the household stays balanced.
3. **Preferences.** Among equally fair splits it picks the best match: what people love (+3), avoid (-4), their skill
   (-1 to +1), anything they said they know how to do (+2), and what they want to learn (+1).
4. **Rotation.** A heavy chore doesn't stay with the same person week after week when someone else could take it.

Fairness always comes before preferences: two people who both love the dishes still don't get all of them.

## Who sees what
| | Private to the person (owner only) | Visible to the whole household |
|---|---|---|
| Their limits | weekly availability, preferences, skills, things they'd like to learn, keywords | nothing |
| Exemption | which weeks they're exempt and why | a count of exempt people (someone who owns nothing that week may be inferred) |
| Offers | that a chore was offered to them; their decline and the reason | that a chore is "being offered", never to whom |
| Plan | why they got a chore ("you enjoy this", "it's your turn") and how their load compares to *their* fair share | the chores, who owns each, its status, and each person's minutes this week |
| Fairness | their own load against their own share | one aggregate: how far the split is from fair at its widest, how many heavy chores rotated, whether planning and admin are shared |
| Week check-in | how the week felt | nothing |
| Contact email | stored on the server | never returned by any API |

The audit trail says that someone was asked or reassigned, never who or why. The agent's spoken or typed replies
are about chores (which the household shares) and the caller's own offers and load, never anyone's preferences.
An automated leak test plants distinctive private values and exercises every household route and tool as every
member through a full lifecycle (profiles, plans, offers, declines, check-ins, completions), failing on any leak.

## Guarding against gaming (self-reports can't be checked)
- **Availability floor** (above), so claiming almost nothing doesn't remove your share.
- **Exemptions are capped** at 2 weeks in any 8, and the reason is never shown, so a real illness is respected
  without becoming a way out. Past the cap the agent suggests lowering availability instead.
- **The ledger counts what was done**, not what was assigned, so accepting chores and not doing them doesn't earn credit.
- **Declining is allowed but visible to you.** If you pass on several requests while carrying less than your share,
  the agent says so, privately, and suggests lowering your availability so the plan stays fair for everyone.
- **A felt-load adjustment is bounded** (at most 20%).

## Honest limits
- **Self-declared inputs.** Availability, preferences and "how the week felt" are reported by the person. The guards
  above bound the effect, but they can't prove honesty. A person who repeatedly reports a heavy week still gets a
  lighter share, within the 20% bound.
- **Chores are indivisible.** With a few large chores, no split can be perfectly even: the report shows the gap the
  limits actually allow ("the fairest the limits allow") rather than hiding it.
- **Ownership still hints at capacity.** The group sees who owns each chore and for how long, so someone who owns a
  chore alone has shown they can do at least that much. Their availability, preferences and reasons stay private.
- **Weights are defaults.** How heavy a chore is, and the premium for mental load, are editable defaults. They are
  reasonable starting points, not facts.
- **"Done" is self-reported.** The agent can't verify a chore was done. A chore left undone shows as "missed".
- **No money.** It doesn't split expenses or arrange paid help; when nobody can take a chore it tells the group a
  decision is needed.

## Why this matters
See [evidence-household-load.md](evidence-household-load.md) for the verified evidence on unequal household load. None
of it tests this agent: whether private limits and an unattributed plan reduce anyone's load or stress is a
hypothesis until real households try it.
