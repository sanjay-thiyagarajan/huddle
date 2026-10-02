# Why Alexa+, and where the fit is weak

## Why a shared voice assistant is a natural home
- **A household device already deals with several people.** Huddle has the same "who is speaking?" problem. In the build, voice identification (a stand-in for Alexa person recognition) picks the profile, and the agent maps that person to their private token.
- **The trigger is natural.** "Alexa, help us plan Mum's care" is something a family would say in the kitchen.
- **The result reads well aloud** (the plan card can be read out).
- **The integration is real:** a self-hosted MCP server over Streamable HTTP (spec 2025-11-25) that the assistant's agent calls.

- **Daily chores are a natural voice use.** "What's on my plate", "I did the bins", "who has the laundry" and "add fix the squeaky door" work as plain-word commands through `ask_household_agent`. Replies are about chores (which the household shares) and the caller's own load, never anyone's private preferences.

## The weak spot, stated plainly
**Answering a private number out loud on a shared speaker can be overheard.** Huddle exists so nobody has to say their number in front of the others. So voice-only answering is only safe when nobody can hear.

## What the build does about it
1. **A privacy gate first.** The voice-only assistant begins by asking whether anyone is close enough to hear. If so, it offers to move the person to their **private phone link** or the **screen**, and saying "someone's here" at any point pauses and offers the same.
2. **It never says a private value aloud.** Replies ask for what's missing and confirm only that an answer is held. Reading it back is opt-in ("read it back"), flagged, and warns that people nearby could hear. A unit test asserts no value or digit appears in any default reply, and a mutation check showed it fails if the confirmation leaks the draft.
3. **The draft stays on the server** and is saved through the MCP tool, so a screen showing the conversation cannot reveal an answer. The captions show only what the assistant says, never what the person said.
4. **Consent is spoken** and required before anything is stored.
5. **Fallbacks, not guessing:** after three misheard turns it hands off to the phone or screen instead of storing a guess.

## What is simulated or unverified (do not overclaim)
- **The Alexa+ experience is a web simulator.** Alexa+ developer tools are preview and select-partner only, so none of this has run on a real device.
- In the simulator, "speaking" is typed text with an optional microphone (browser speech recognition) and browser text-to-speech.
- **Reminders do not use Alexa.** They are delivered by Huddle's own scheduler: in-app (while a page is open), optional email, and the device share sheet. I have not verified what Alexa+ supports for notifications or quiet responses, and no feature here depends on them.
- Voice ID accuracy has only been measured on synthetic voices.
- On a screenless speaker, a person can't check what was understood without hearing it back, which is the trade-off behind the opt-in read-back. A misheard number could be saved. The phone link and the screen are the safer ways to confirm.

## Where the fit is strongest
An Echo with a screen, or the phone link, for the private part, with the assistant as the household's front door and identity. A speaker alone is good for starting, nudging and reading the result, and only for answering when someone is genuinely alone.
