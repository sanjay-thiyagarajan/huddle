# Demo video script (target 2:40, hard limit under 3:00)

Rules: public on YouTube or Vimeo, English, no music (or properly licensed), no Amazon/Alexa logos (plain-text names
only), and the video must clearly show that the Alexa+ experience is **simulated** and that voice ID is a **stand-in**.
Record on a clean `make dev` run in mock mode. Everything on screen below exists today.

**The one idea to land:** a home carries three sizes of load (the heavy, the daily, the occasional). Huddle handles all
three the same private, fair way, in one household, and what you carry in one counts in the others.

| Time | Beat | On screen | Say (plain, not salesy) |
|---|---|---|---|
| 0:00-0:12 | The problem | Title text | "In most homes the load piles up on one person. Saying 'I can't take more' out loud is hard." |
| 0:12-0:40 | Alexa first: the heavy | The **Try a decision** tab, with its on-screen label "Simulated voice assistant. Not a real Alexa+ device." Start a care decision for Maya, Ben and Chen and tick **Voice-only mode**. "Is anyone close enough to hear you?" Maya answers aloud; captions show only what the assistant says. Ben says someone's here and is moved to his phone link | "On a shared speaker an answer can be overheard. So it asks first, never says your answer back, and offers your phone instead." Say once: "voice recognition here is a stand-in." |
| 0:40-1:10 | The plan | Chen answers on his own phone, from his private link (he is "by link" by default; show the phone page). The plan appears: who owns which task, the gap in bands, "Your part" with only your own hours | "The family gets who owns what, never anyone's limits." Say once: "Huddle doesn't hire or pay anyone; if the family can't cover it, it suggests paid help." |
| 1:10-1:40 | The daily: chores | The **Home** tab, a household of the same three (set up before recording, with **Share a parent's care** already closed for it). "Add a starter set of chores", "Plan the week". The fairness card says "Care already taken on is counted in everyone's share". Open Maya's private panel: "Cooking: avoid" | "One household, the same people. The care Maya took on counts in her chores, and nobody sees who set which limit." |
| 1:40-2:00 | By words | In the agent box, spoken or typed: "add fix the squeaky door". It is offered to one person; they accept. Then "what's on my plate". Open **MCP tool calls** under the box: `ask_household_agent` | "A new chore is offered to the best fit. They can say no, and then the next person is asked, privately." |
| 2:00-2:15 | My time (cut first if over) | **My time**: "dinner with Priya Thursday 7pm"; the clash is explained with options | "Your own week sits across all of it, and stays yours." |
| 2:15-2:38 | Under the hood | In the simulator, open **MCP tool calls** (the tools the assistant just called, names and timing only). Then the terminal: `make mcp-inspect` scrolling the tool list (titles, hints), then `make test` with the leak test passing; the README architecture diagram | "A self-hosted MCP server over Streamable HTTP, written for an assistant that has never seen it. A leak test fails if anyone's private limit appears in anything another member can fetch." |
| 2:38-2:50 | Honest limits | One slide: not cryptographic; two-person limit; voice ID is a stand-in; simulated Alexa+; [real user-test numbers if any] | State the limits plainly. Show real numbers only if `docs/user-test.md` has them. |

Why this order: the entry is judged in the Alexa+ track, so the spoken exchange and the privacy gate come first, while attention is highest, and the MCP server gets a visible beat of its own. Care is also the plan's main story.

## Before recording
- [ ] Fresh clone runs `make dev` without credentials
- [ ] Set up the Home household (Maya, Ben, Chen) and close a care decision for it, so the fairness card shows the care line
- [ ] `make dev` running in a second terminal for `make mcp-inspect`
- [ ] Rehearse once; time it under 2:50
- [ ] No tokens, personal data or real names on screen (use Maya, Ben, Chen)
- [ ] Say "voice recognition here is a stand-in" if voice ID appears
- [ ] If AWS parts ran, add the terminal clip; if not, say nothing about them
