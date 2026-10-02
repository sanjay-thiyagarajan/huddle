# Novelty search (plan P0 gate)

Run 2026-10-02 with web search plus reading the public README or landing page of each close hit.
**Limits:** web search only. I did not browse the Devpost project gallery, so entries not on GitHub or
the open web are unseen, and new entries will keep appearing until Oct 23. Re-check the gallery by hand
before submitting. Page summaries were produced by a small model reading each page; treat them as
leads to verify, not quotes.

## Result in one line
**No near-duplicate of the core mechanic found** (each person gives private limits; the engine returns one
plan or split without showing or attributing who limited it). **The surrounding space is crowded**: at
least six other Alexa+ entries use a self-hosted MCP server plus a simulator, and one uses the same
architecture as Huddle. The differentiator has to be the mechanic and the evidence, not the stack.

## Same hackathon (Alexa+ track)
| Entry | What it is | Overlap with Huddle | Difference |
|---|---|---|---|
| [HomeOps](https://github.com/solanaminter/alexa-homeops) | Family household coordinator; 16 MCP tools (calendar, chores, grocery, school, approvals, audit); Strands agent on Bedrock; React simulated Alexa+; MIT | **Highest on architecture:** self-hosted MCP over Streamable HTTP, Strands on Bedrock, React simulator | Coordinates tasks behind approval gates and a hash-chained audit log. No private per-person limits or group matching found in the README. |
| [KindHandoff](https://github.com/shi1720/Amazon-Developer-Hackathon) | Repairs a disrupted family support plan when a helper cancels; private single-use invites; MCP 2025-11-25 over Streamable HTTP; Firebase | **Closest on theme** (family care) and on private single-use links | Proposes replacements from availability and shows the coordinator why candidates were excluded ("visible exclusions"), the opposite of non-attribution. No private hours, money or dealbreaker limits found. No Bedrock or Strands. |
| [HomePilot](https://github.com/meryl96sushna-eng/HomePilot-AlexaPlus-Hackathon) | Simulated Alexa+ household planner with conflict detection and confirmation gates; Node.js | Simulated Alexa+, household planning | No MCP, Bedrock or Strands found; no per-person private data. |
| [council-mcp](https://glama.ai/mcp/servers/arshadalkaladi/council-mcp) | One user asks; four internal "perspectives" return a recommendation with minority views | "Decision" framing | Single-user deliberation, not group inputs. |
| [guptachetan1995/alexa-plus](https://github.com/guptachetan1995/alexa-plus), [hermx-proofgate](https://github.com/senih25/hermx-proofgate-amazon-2026) | MCP servers where every device action needs a human Confirm | MCP plus a simulated client | Approval gating, not group decisions. |

## Products and research
- **[CareSplit](https://www.caresplit.app/guides/best-sibling-caregiving-coordination-app-2026)** (iOS, launching Apr 30, 2026), CircleCare, Caring Village: sibling care coordination with a shared task board, expense splitting and a *fairness dashboard*. Their pitch is transparency ("every dollar is logged and visible to all siblings"). I found nothing about private limits feeding a computed split. Huddle takes the opposite stance on purpose, and also does **not** split expenses or track tasks (out of scope), so it complements rather than competes with these.
- **Group trip and budget apps** (WePlanify, Splitwise, and similar): polls, shared budgets, settle-up. Advice to "ask everyone for an anonymous budget range" appears in travel articles, which is a manual version of the same need, done with a survey and an organiser who sees everything.
- **Prior art in research:** privacy-preserving scheduling with secure two-party computation ([KSS19, web application](https://encrypto.de/papers/KSS19.pdf)) and privacy-preserving group purchasing decisions ([arXiv 2505.11094](https://arxiv.org/pdf/2505.11094)). These give cryptographic guarantees; Huddle gives no-attribution plus bucketing only. Don't claim novelty for "private group decision" as a concept.
- **MCP voting servers** ([voting-mcp](https://glama.ai/mcp/servers/HrishiKabra/voting-mcp), [quorum-mcp](https://github.com/terradev-cloud/quorum-mcp)): social-choice aggregation tools for agents, not household people with private numeric limits.
- **Alexa itself:** voice profiles and skill personalization give per-person recognition; I found no skill that aggregates household members' private limits into one plan.

## What this means for Huddle
1. **Defensible claim:** "Private limits in, one plan out, nobody told who limited it", for people at one device plus a remote link, with the limits stated honestly. I found no entry doing this. That is a finding about my search, not proof.
2. **Do not claim** "first", "secure" or "encrypted"; MPC research exists and Huddle is not that.
3. **Architecture alone will not stand out.** HomeOps matches the MCP + Strands + Bedrock + React simulator stack. What Huddle has that the entries I read do not: the automated leak test, the k-rule and bucketing, the failure path with stated defaults, and (once collected) real-group results. Lead with those. **Real AWS runs and real-user results are the gaps** that most separate a strong entry from a similar one.
4. **Possible borrowing:** KindHandoff's single-use invites and HomeOps' audit log show judges are seeing "approval" and "audit" ideas. A host-visible, value-free audit trail (who answered when, never what) would fit Huddle; not built.
5. **Care mode vs CareSplit-style apps:** position as the *decision before the logging*: agree on a split with private limits, then use a tracker. Avoid implying Huddle replaces them.
