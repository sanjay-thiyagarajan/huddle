# Demo video script (target 2:40, hard limit under 3:00)

Rules: public on YouTube or Vimeo, English, no music (or properly licensed), no Amazon/Alexa logos
(plain-text names only), and the video must clearly show that the Alexa+ experience is **simulated**
and that voice ID is a **stand-in**. Record on a clean `make dev` run in mock mode.
Everything on screen below exists today unless marked [NOT YET].

| Time | Beat | On screen | Say (plain, not salesy) |
|---|---|---|---|
| 0:00-0:15 | Hook | Title text, then the start screen | "Some decisions stall because nobody wants to say their real number out loud." |
| 0:15-0:35 | The problem, in one example | Start screen (care preselected): read the sibling example on screen | "Three siblings share a parent's care. Nobody wants their limit to be the one that decides. Huddle asks each of them privately." |
| 0:35-1:45 | **Care mode (main story)** | "Help us plan Mum's care". Edit the care need (open the editor). Maya by voice (type or speak the sentence); switch to Ben; "Show what the server holds" (answers stored, no values); Chen answers on his own phone via the link. Reveal: gap in bands, who owns what (no hours), each person's private "Your part", ways to close the gap, the assignment caveat | "Three siblings, one in another city. The server holds the numbers; nobody sees them. The group sees the gap, a split that respects every limit, and doesn't say who set which one." |
| 1:30-1:45 | Voice-only moment (can replace part of the care walkthrough) | Toggle "Voice-only mode"; the assistant asks "is anyone close enough to hear you?"; Ben says someone is here and is moved to his phone link. Captions show only what the assistant says | "On a shared speaker, answering aloud can be overheard. So Huddle asks first, never says your answer back, and moves you to your phone if someone's near." |
| 1:45-2:05 | Same family, next decision | "What should the family decide next?" then "Plan a weekend": Maya's panel shows the optional private care-load hint; a two-second flash of the household plan list. If time is tight, show the two-person banner here instead | "Same family, no retyping. Whoever carries heavy care tasks gets a private hint, only if they want it." |
| 2:05-2:20 | Failure path + check-in | Short 45-second deadline; one sibling never answers; reminder banner; defaults applied and stated. Then the check-in and the unattributed summary, and "Start the next round" (if the check-in flags discomfort) | "If someone doesn't answer: a reminder, then a stated default. The next day each person privately checks in and the group sees only a summary." |
| 2:20-2:38 | Under the hood (optional 3 seconds: "Read it aloud" on the plan card) | Terminal: `make test` with the leak test passing; architecture diagram from the README; [NOT YET: Strands agent on Bedrock, AgentCore] | "An MCP server over Streamable HTTP, called by the simulator. A leak test fails if anyone's value appears in anything another person can call." |
| 2:38-2:50 | Honest limits + results | One slide: not cryptographic; two-person limit; voice ID is a stand-in; simulated Alexa+; [NOT YET: real user-test numbers]. Close with the trip mode in two seconds: "same engine, any group decision" | State the limits plainly. Show real numbers only if `docs/user-test.md` has them. |

## Before recording
- [ ] Fresh clone runs `make dev` without credentials
- [ ] Rehearse once; time it under 2:50
- [ ] No tokens, personal data or real names on screen (use Maya, Ben, Chen)
- [ ] Voice shown only as typed or spoken text; say "voice recognition here is a stand-in"
- [ ] If AWS parts ran, add the terminal clip; if not, say nothing about them
