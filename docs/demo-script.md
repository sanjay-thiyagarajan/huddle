# Demo video script (target 2:40, hard limit under 3:00)

Rules: public on YouTube or Vimeo, English, no music (or properly licensed), no Amazon/Alexa logos (plain-text names
only), and the video must clearly show that the Alexa+ experience is **simulated** and that voice ID is a **stand-in**.
Record on a clean `make dev` run in mock mode. Everything on screen below exists today.

**The one idea to land:** a home carries three sizes of load (the heavy, the daily, the occasional). Huddle handles all
three the same private, fair way, in one household, and what you carry in one counts in the others.

| Time | Beat | On screen | Say (plain, not salesy) |
|---|---|---|---|
| 0:00-0:15 | The problem | Title text, then the **Home** tab's setup page | "In most homes the load piles up on one person. Saying 'I can't take more' out loud is hard." |
| 0:15-0:50 | The daily: chores | Create the household (Maya, Ben, Chen). "Add a starter set of chores", "Plan the week". Show the fairness card. Open Maya's private panel: set hours, "Cooking: avoid" | "Everyone tells Huddle privately what they can take on. It splits the week fairly, and nobody sees who set which limit." |
| 0:50-1:10 | Ad hoc, by words | In the agent box: "add fix the squeaky door". It is offered to one person; they accept. Show the board: no one can tell who was asked | "A new chore is offered to the best fit. They can say no, and then the next person is asked, privately." |
| 1:10-1:50 | The heavy: care | **Share a parent's care** for the same household. Each member answers their part privately (switch profiles). The plan appears: who owns which task, the gap in bands, "Your part" with only your own hours | "Same people, no retyping. The family gets who owns what, never anyone's limits." Say once: "Huddle doesn't hire or pay anyone; if the family can't cover it, it suggests paid help." |
| 1:50-2:10 | They connect | Plan the week again: the fairness card says "Care already taken on is counted in everyone's share"; the carer's chore load is lighter ("of care you've taken on") | "The care Maya took on counts in her chores. She isn't handed a full load on top." |
| 2:10-2:25 | Alexa and privacy | Voice-only mode: "is anyone close enough to hear you?"; Ben moved to his phone link. Captions show only what the assistant says | "On a shared speaker, answering aloud can be overheard. So it asks first, and never says your answer back." |
| 2:25-2:40 | Under the hood | Terminal: `make test` with the leak test passing; the README's architecture diagram; the MCP tool list | "An MCP server over Streamable HTTP. A leak test fails if anyone's private limit appears in anything another member can fetch." |
| 2:40-2:50 | Honest limits | One slide: not cryptographic; two-person limit; voice ID is a stand-in; simulated Alexa+; [real user-test numbers if any] | State the limits plainly. Show real numbers only if `docs/user-test.md` has them. |

## Before recording
- [ ] Fresh clone runs `make dev` without credentials
- [ ] Rehearse once; time it under 2:50
- [ ] No tokens, personal data or real names on screen (use Maya, Ben, Chen)
- [ ] Say "voice recognition here is a stand-in" if voice ID appears
- [ ] If AWS parts ran, add the terminal clip; if not, say nothing about them
