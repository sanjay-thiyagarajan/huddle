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

- **Hear and see the day.** "What's my day" (or the **Today** card) gives the person's own commitments, any clash,
  chores due, offers waiting and family decisions waiting for their private answer, and the next free hour, as sentences
  an assistant can read aloud. Nothing about anyone else is in it, and no private limit is ever spoken.
- **Bring a calendar in, and take it out.** The person exports an `.ics` file from Outlook, Google or Apple Calendar and
  reads it in (or pastes a read-only calendar address, which Huddle re-reads about hourly, or at once with **Read it again now**). Each event becomes one of
  their own private commitments; reading the same file again updates rather than duplicates, and something they removed
  here doesn't come back. They can export their commitments, or their planned chores (as all-day entries), as `.ics`.
- **Opt-in reminders.** "Starting soon" (30 minutes ahead) and a Sunday-evening week-ahead note, on the person's page and,
  if the host gave an address, by email. Off until chosen, with quiet hours. "Starting soon" shows as a banner at the top
  of My time, and a browser pop-up if the person allows it, **only while that page is open in a tab**. They don't come from
  the speaker. In the simulator, an opt-in toggle also speaks replies and the reminder aloud with the browser's voice (see
  [alexa-fit.md](alexa-fit.md)).

## What is private
| | Only the owner | Anyone else |
|---|---|---|
| Commitments (titles, times, circle) | yes | nothing; a shared find-a-time shows only its chosen time to attendees |
| Imported calendar events, a subscribed calendar address, reminder settings | yes | nothing; the address is never returned by any route or tool, not even to its owner |
| Rules, learned preferences | yes | nothing |
| Why they answered works / maybe / can't | yes | nothing |
| A find-a-time result | | best time, fit (everyone / some would move things / closest), a count only when 3 or more answered |

The automated leak test plants a distinctive private commitment title and rule and exercises every time route and the
scheduling conversation as the other household members. It also plants a distinctive imported event and a calendar
address and calls every calendar, briefing, export and reminder route and tool as everyone, failing if another member
sees the event, or if anyone is ever sent the address back. Reminder bookkeeping is kept out of the household's shared
audit trail, so the time of someone's commitment isn't visible there.

## Agent and tools
The conversation is deterministic and works with no AWS credentials (`server/agent/schedule_agent.py`,
`server/engine/schedule_chat.py`). The same abilities are MCP tools: `get_my_time`, `add_commitment`,
`update_commitment`, `set_schedule_rules`, `start_gathering`, `answer_gathering`, `ask_schedule_agent`,
`get_daily_briefing`, `import_calendar`, `export_calendar`, `subscribe_calendar`, `set_reminder_prefs`.

## Limits
- Times are floating local times: no time zones. Commitments are entered by the person or read from a calendar file or
  address they provide. **This is not a calendar sync or an integration with Google, Outlook or Apple:** there is no
  sign-in to those services, nothing is written back, and a change in Huddle doesn't reach the original calendar.
- Every skipped event is counted with its reason (for example "1 longer than 14 hours"), never named. A reminder that an event ending the next day by mistake is 25 hours long is the most common cause.
- Calendar files: Huddle reads plain events and plainly daily or weekly repeats (with an end date or count, and removed
  dates). All-day events, monthly or every-other-week repeats, several weekdays in one rule, changed single days of a
  series, and events shorter than 5 minutes or longer than 14 hours are skipped and counted, not guessed. A time written
  in UTC or with a time zone is used as written, with no conversion; the import says how many were like that. Limits: 2 MB
  and 500 events per file.
- A subscribed address must be https (or webcal), is read-only, is refused if it points inside a private network, is read
  at most hourly with a 10 second timeout and a 2 MB cap, and may redirect only within the same host. The name is checked
  before the request, so a host that changes its answer in between could slip past; it is a guard, not a guarantee. After
  five failed reads in a row Huddle stops trying and says so.
- Reminders: "starting soon" is a banner and optional browser pop-up on the My time page, which works only while the page
  is open (the pop-up is not a push notification), plus email only if the host configured SMTP and the person gave an
  address. There is no SMS, push or Alexa notification, and nothing here depends on one. The Sunday digest has no banner:
  it is email only. Because times are floating, "starting soon" uses the offset the
  person's browser reports; if it's wrong the reminder is early or late.
- The half-finished conversation (a clash waiting for an answer) is held in server memory; a restart only costs the
  person repeating their last sentence.
- Find-a-time with two people can let each infer the other's limit; the result says so.
- Voice answers to a find-a-time are handed to the screen; the spoken flow covers the other decisions.
- Whether this reduces anyone's stress or double-booking is untested with real households.
