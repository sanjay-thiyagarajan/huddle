# Your time: personal and family commitments in one private schedule

Where the household agent decides who carries which chore, **My time** looks after one person's hours across
family, friends, work and personal life, and settles clashes by talking to them.

## What a person can do
- **Say or type** a commitment: "dinner with Priya Thursday 7pm for 2 hours", "standup every Monday 9:30 for 30
  minutes", "school concert Thursday 6pm, can't move". The agent understands day, time, length, repeat, who it's
  with (family, friends, work or personal), how movable it is and how much it matters. A missing day or time is asked
  for, never guessed.
- **Settle a clash by conversation.** When two things overlap, the agent says what clashes, suggests one way out and
  gives the reason ("family comes above friends in your rules"), then waits. They answer "yes", "keep both", "skip the
  new one", "move it to Friday 7pm", "move the other one" or a number. Nothing is added until they answer.
- **Teach it rules once.** Which circle wins a clash, protected times (Sunday mornings), work hours, the most evenings
  out in a week, buffer between things. After two consistent choices the agent offers to make it a rule.
- **Find a time** with friends, colleagues or family. People in the household answer from their own schedule (the agent
  suggests works / could move things / can't, with a reason only that person sees). Guests get a private link. The
  result is the best time and the trade-off, never who could not make which. The chosen time lands on each
  attendee's own schedule; a "could move things" becomes a tentative item they confirm.
- **See the week** by circle, with free time, and a **suggested chore availability** (a quarter of the free time) they
  can choose to save. The household planner only ever receives the number they save, not the calendar.

## What is private
| | Only the owner | Anyone else |
|---|---|---|
| Commitments (titles, times, circle) | yes | nothing; a shared find-a-time shows only its chosen time to attendees |
| Rules, learned preferences | yes | nothing |
| Why they answered works / maybe / can't | yes | nothing |
| A find-a-time result | | best time, fit (everyone / some would move things / closest), a count only when 3 or more answered |

The automated leak test plants a distinctive private commitment title and rule and exercises every time route and the
scheduling conversation as the other household members.

## Agent and tools
The conversation is deterministic and works with no AWS credentials (`server/agent/schedule_agent.py`,
`server/engine/schedule_chat.py`). The same abilities are MCP tools: `get_my_time`, `add_commitment`,
`update_commitment`, `set_schedule_rules`, `start_gathering`, `answer_gathering`, `ask_schedule_agent`.

## Limits
- Times are floating local times: no time zones, and no sync with Google, Outlook or Apple calendars. Commitments are
  entered by the person.
- The half-finished conversation (a clash waiting for an answer) is held in server memory; a restart only costs the
  person repeating their last sentence.
- Find-a-time with two people can let each infer the other's limit; the result says so.
- Voice answers to a find-a-time are handed to the screen; the spoken flow covers the other decisions.
- Whether this reduces anyone's stress or double-booking is untested with real households.
