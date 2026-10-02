# Demo video script (target 2:40, hard limit under 3:00)

Rules: public on YouTube or Vimeo, English, no music (or properly licensed), no Amazon/Alexa logos
(plain-text names only), and the video must clearly show that the Alexa+ experience is **simulated**
and that voice ID is a **stand-in**. Record on a clean `make dev` run in mock mode.
Everything on screen below exists today unless marked [NOT YET].

| Time | Beat | On screen | Say (plain, not salesy) |
|---|---|---|---|
| 0:00-0:15 | Hook | Title text, then the start screen | "Some decisions stall because nobody wants to say their real number out loud." |
| 0:15-0:35 | Weekend plan, fast | "Alexa, plan our Saturday". Maya and Ben answer privately; reveal with one plan and the trade-off, plus the two-person warning banner | "Two people. Each answers privately. One plan, and the trade-off without naming who." Point at the banner: "With two people the other can infer your number, and Huddle says so." |
| 0:35-1:55 | **Care mode (main story)** | "Help us plan Mum's care". Edit the care need (open the editor). Maya by voice (type or speak the sentence); switch to Ben; "Show what the server holds" (answers stored, no values); Chen answers on his own phone via the link. Reveal: gap in bands, split, ways to close the gap, the assignment caveat | "Three siblings, one in another city. The server holds the numbers; nobody sees them. The group sees the gap, a split that respects every limit, and doesn't say who set which one." |
| 1:55-2:15 | Failure path + check-in | Short 45-second deadline; one sibling never answers; reminder banner; defaults applied and stated. Then the check-in and the unattributed summary, and "Start the next round" (if the check-in flags discomfort) | "If someone doesn't answer: a reminder, then a stated default. The next day each person privately checks in and the group sees only a summary." |
| 2:15-2:35 | Under the hood (optional 3 seconds: "Read it aloud" on the plan card) | Terminal: `make test` with the leak test passing; architecture diagram from the README; [NOT YET: Strands agent on Bedrock, AgentCore] | "An MCP server over Streamable HTTP, called by the simulator. A leak test fails if anyone's value appears in anything another person can call." |
| 2:35-2:50 | Honest limits + results | One slide: not cryptographic; two-person limit; voice ID is a stand-in; simulated Alexa+; [NOT YET: real user-test numbers]. Close with the trip mode in two seconds: "same engine, any group decision" | State the limits plainly. Show real numbers only if `docs/user-test.md` has them. |

## Before recording
- [ ] Fresh clone runs `make dev` without credentials
- [ ] Rehearse once; time it under 2:50
- [ ] No tokens, personal data or real names on screen (use Maya, Ben, Chen)
- [ ] Voice shown only as typed or spoken text; say "voice recognition here is a stand-in"
- [ ] If AWS parts ran, add the terminal clip; if not, say nothing about them
