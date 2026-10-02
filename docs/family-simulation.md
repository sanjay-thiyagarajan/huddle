# Fictional family simulation (synthetic voices)

Run 2026-10-02 by `python tests/family_sim.py`.

**This is a fictional family spoken by text-to-speech voices (macOS `say`). No human took part.** It checks
that the voice pipeline works end to end with real audio: speaker identification, Whisper transcription,
the voice-only dialogue, the MCP tool, the private store and the engine. It tells us **nothing** about
whether Huddle makes decisions easier for real people; that needs the real-group test in `docs/user-test.md`.

The cast: Maya, Ben and Chen, three invented siblings sharing a parent's care.

## What happened
- Speaker identified correctly: **12/12** utterances.
- Mean Whisper word error on these scripted sentences: **0.0%**.
- All three answers stored through the MCP tool: **True**.
- No assistant reply contained a digit (voice-only privacy rule): **True**.

## Caveats (read before quoting any number above)
- Clean text-to-speech with no background noise: Whisper and speaker ID are at their best here. Real microphones, rooms and moods will be worse.
- **The weakest identification was the shortest line.** The closing "Save it." clips scored 0.53 to 0.61 cosine against a threshold of 0.50 (lowest overall: Ben step 3, 0.53). A one-second confirmation is a fragile thing to identify a speaker from; with real voices it may be missed, so the dialogue's confirm step must not depend on speaker ID alone.
- One run, one fictional family, three voices that happen to be very different from each other.

## The result the family got
The plan needs 30 h/week and $1,800/month. After fitting everyone's private limits, the gap is 0-5 h per week and $250-500 per month.

Who owns what (what the whole group sees; no hours):

- Maya: Appointments and transport; Meals
- Ben: Daily check-in; Finances and paperwork
- Chen: Overnight cover

Each sibling's own hours (each returned only to that sibling's token; shown together here only because this family is fictional):

- Maya: Appointments and transport 6 h; Meals 6 h
- Ben: Daily check-in 5 h; Finances and paperwork 3 h
- Chen: Overnight cover 6 h

Gap in hours: 0-5 h; gap in money: $250-500.

## Step by step
| Speaker | Step | Scripted line | Whisper heard | Word error | Identified as (cosine) | Dialogue stage after |
|---|---|---|---|---|---|---|
| Maya | 0 | Just me, nobody is around. | Just me, nobody is around. | 0% | Maya (0.85) | consent |
| Maya | 1 | Yes, I agree to answer. | Yes, I agree to answer. | 0% | Maya (0.81) | collect |
| Maya | 2 | I can do about twelve hours a week and six hundred dollars a month, but not nights. | I can do about 12 hours a week and $600 a month, but not nights. | 0% | Maya (0.91) | confirm |
| Maya | 3 | Save it. | Save it. | 0% | Maya (0.61) | saved |
| Ben | 0 | Just me, the house is quiet. | Just me, the house is quiet. | 0% | Ben (0.82) | consent |
| Ben | 1 | Yes, I agree to answer. | Yes, I agree to answer. | 0% | Ben (0.8) | collect |
| Ben | 2 | I live far away. I can give eight hours a week and five hundred dollars a month. | I live far away, I can give 8 hours a week and $500 a month. | 0% | Ben (0.87) | confirm |
| Ben | 3 | Save it. | Save it. | 0% | Ben (0.53) | saved |
| Chen | 0 | Just me, I am alone. | Just me, I am alone. | 0% | Chen (0.75) | consent |
| Chen | 1 | Yes, I agree to answer. | Yes, I agree to answer. | 0% | Chen (0.8) | collect |
| Chen | 2 | I can do six hours a week and four hundred dollars a month, but I can't do transport. | I can do 6 hours a week and $400 a month, but I can't do transport. | 0% | Chen (0.9) | confirm |
| Chen | 3 | Save it. | Save it. | 0% | Chen (0.59) | saved |

