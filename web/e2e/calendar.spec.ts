import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import type { Page } from "@playwright/test";

const myTime = (page: Page) => page.getByRole("button", { name: "My time" }).click();
const stamp = (d: Date) => `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}00`;

/** A calendar file as Outlook or Google would export it: one event today, in the evening (floating time). */
function todayIcs(title: string) {
  const start = new Date(); start.setHours(20, 0, 0, 0);
  const end = new Date(start); end.setHours(21);
  return [
    "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT", "UID:e2e-1", `SUMMARY:${title}`,
    `DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`, "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
}

test("calendar file in, today's briefing, calendar file out, reminders and accessibility", async ({ page }) => {
  await page.goto("/?tab=home");
  await page.getByRole("button", { name: "Create the household" }).click();
  await myTime(page);

  const today = page.getByRole("region", { name: "Today", exact: true });
  await expect(today).toContainText("your calendar is clear");

  // read a calendar file: it becomes this person's own commitments, and today's briefing reads it back
  await page.getByLabel("Calendar file (.ics)").setInputFiles({
    name: "work.ics", mimeType: "text/calendar", buffer: Buffer.from(todayIcs("Quarterly review")),
  });
  await expect(page.getByText(/Read 1 new, 0 updated, 0 unchanged/)).toBeVisible();
  await expect(today).toContainText("Quarterly review at 20:00");
  await expect(page.getByRole("region", { name: "Your week", exact: true })).toContainText("Quarterly review");

  // reading the same file again updates rather than duplicating
  await page.getByLabel("Calendar file (.ics)").setInputFiles({
    name: "work.ics", mimeType: "text/calendar", buffer: Buffer.from(todayIcs("Quarterly review")),
  });
  await expect(page.getByText(/Read 0 new, 0 updated, 1 unchanged/)).toBeVisible();

  // hand it back as a file
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export my commitments" }).click()]);
  expect(download.suggestedFilename()).toBe("huddle-my-time.ics");
  const text = await readFile((await download.path())!, "utf8");
  expect(text).toContain("BEGIN:VCALENDAR");
  expect(text).toContain("SUMMARY:Quarterly review");
  expect(text).toContain("UID:e2e-1"); // the calendar's own id is kept, so it isn't duplicated when added back

  // the agent reads the day, and points to the export for a file
  await page.getByLabel("Say or type").fill("what's my day");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("log", { name: "What the scheduling agent says" })).toContainText("Quarterly review at 20:00");

  // a bad file is a calm message, not a crash
  await page.getByLabel("Calendar file (.ics)").setInputFiles({ name: "x.ics", mimeType: "text/calendar", buffer: Buffer.from("not a calendar") });
  await expect(page.getByRole("alert").filter({ hasText: "doesn't look like a calendar" })).toBeVisible();

  // an address that isn't https is refused, and the address is never shown back
  await page.getByLabel(/Calendar address/).fill("http://example.com/secret-token.ics");
  await page.getByRole("button", { name: "Follow" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /https/ })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toContain("secret-token");

  // reminders are off until chosen
  const toggle = page.getByRole("button", { name: "When something starts soon" });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Set quiet hours" }).click();
  await expect(page.getByText("Quiet from 22:00 until 07:00.")).toBeVisible();

  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
});

test("starting-soon reminder shows as a banner on My time, only once it is switched on", async ({ page }) => {
  await page.goto("/?tab=home");
  await page.getByRole("button", { name: "Create the household" }).click();
  await myTime(page);

  // an event 15 minutes from now, read in from a calendar file
  const start = new Date(Date.now() + 15 * 60_000);
  const end = new Date(start.getTime() + 30 * 60_000);
  const ics = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT", "UID:e2e-soon", "SUMMARY:Team sync",
    `DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`, "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
  await page.getByLabel("Calendar file (.ics)").setInputFiles({ name: "soon.ics", mimeType: "text/calendar", buffer: Buffer.from(ics) });
  await expect(page.getByText(/Read 1 new/)).toBeVisible();

  // off by default: no banner
  const banner = page.getByRole("alert", { name: "Starting soon" });
  await expect(banner).toHaveCount(0);

  // turn it on: the banner names the event and how long is left
  await page.getByRole("button", { name: "When something starts soon" }).click();
  await expect(banner).toContainText(/Team sync starts in 1[0-5] minutes?/, { timeout: 15_000 });

  // quiet hours covering now silence it; clearing them brings it back
  await page.getByLabel("Quiet from").fill("00:00");
  await page.getByLabel("until").fill("23:59");
  await page.getByRole("button", { name: "Set quiet hours" }).click();
  await expect(banner).toHaveCount(0, { timeout: 15_000 });
  await page.getByRole("button", { name: "No quiet hours" }).click();
  await expect(banner).toContainText("Team sync", { timeout: 15_000 });

  // turning it off removes it again
  await page.getByRole("button", { name: "When something starts soon" }).click();
  await expect(banner).toHaveCount(0, { timeout: 15_000 });
});

test("my time speaks the day, agent replies and the starting-soon reminder when asked, and can listen", async ({ page }) => {
  // The browser's voice and microphone are stubbed: record what is said, and "hear" a fixed sentence.
  await page.addInitScript(() => {
    const said: string[] = [];
    (window as unknown as { __said: string[] }).__said = said;
    Object.defineProperty(window, "speechSynthesis", {
      value: { speak: (u: { text: string }) => said.push(u.text), cancel: () => undefined },
      configurable: true,
    });
    (window as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class { text: string; constructor(t: string) { this.text = t; } };
    (window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = class {
      lang = ""; onresult: ((e: unknown) => void) | null = null; onend: (() => void) | null = null;
      start() { setTimeout(() => { this.onresult?.({ results: [[{ transcript: "what's my day" }]] }); this.onend?.(); }, 50); }
      stop() { /* nothing to stop */ }
    };
  });
  const said = () => page.evaluate(() => (window as unknown as { __said: string[] }).__said);

  await page.goto("/?tab=home");
  await page.getByRole("button", { name: "Create the household" }).click();
  await myTime(page);

  const start = new Date(Date.now() + 15 * 60_000);
  const end = new Date(start.getTime() + 30 * 60_000);
  const ics = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT", "UID:e2e-voice", "SUMMARY:Voice check",
    `DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`, "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
  await page.getByLabel("Calendar file (.ics)").setInputFiles({ name: "v.ics", mimeType: "text/calendar", buffer: Buffer.from(ics) });
  await expect(page.getByText(/Read 1 new/)).toBeVisible();

  // nothing is spoken until asked; the button speaks the day
  expect(await said()).toEqual([]);
  await page.getByRole("button", { name: "Read my day aloud" }).click();
  await expect.poll(async () => (await said()).join(" ")).toContain("Voice check");

  // with the toggle on, the microphone button hears "what's my day" and the reply is spoken
  await page.getByLabel(/Speak replies and reminders aloud/).check();
  const before = (await said()).length;
  await page.getByRole("button", { name: "Speak", exact: true }).click();
  await expect(page.getByRole("log", { name: "What the scheduling agent says" })).toContainText("Voice check");
  await expect.poll(async () => (await said()).length).toBeGreaterThan(before);

  // the reminder is spoken once, not on every poll
  await page.getByRole("button", { name: "When something starts soon" }).click();
  await expect.poll(async () => (await said()).filter((s) => s.startsWith("Reminder: Voice check")).length).toBe(1);
  await page.waitForTimeout(12_000); // more than two polls
  expect((await said()).filter((s) => s.startsWith("Reminder: Voice check")).length).toBe(1);

  // switched off: a new reply is silent
  await page.getByLabel(/Speak replies and reminders aloud/).uncheck();
  const quiet = (await said()).length;
  await page.getByLabel("Say or type").fill("what's my week");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("log", { name: "What the scheduling agent says" })).toContainText("Agent:");
  expect((await said()).length).toBe(quiet);
});
