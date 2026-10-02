import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

// Chen answers on his own page. The host sees honest delivery results; Chen sees a reminder banner and,
// if he allowed it, a browser notification. No SMTP is configured here, so email must say "skipped".
async function openChen(page: Page, context: import("@playwright/test").BrowserContext) {
  const link = (await page.locator(".linkbox code").innerText()).trim();
  const chen = await context.newPage();
  await chen.addInitScript(() => {
    const notes: { title: string; body: string }[] = [];
    (window as unknown as { __notes: typeof notes }).__notes = notes;
    (window as unknown as { Notification: unknown }).Notification = class {
      static permission = "granted";
      static requestPermission() { return Promise.resolve("granted"); }
      constructor(title: string, opts: { body: string }) { notes.push({ title, body: opts.body }); }
    };
  });
  await chen.goto(link);
  await expect(chen.getByRole("heading", { name: /Hi Chen/ })).toBeVisible();
  return chen;
}

test("host nudge: honest delivery results, reminder banner and notification on Chen's page, rate limit", async ({ page, context }) => {
  await page.goto("/?tab=decisions");
  await page.getByLabel("Email for reminders for Chen (optional)").fill("chen.sentinel@example.test");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByRole("button", { name: /^Chen/ }).click();
  const chen = await openChen(page, context);
  await expect(chen.getByText(/Reminder:/)).toHaveCount(0); // nothing yet

  await page.getByRole("button", { name: "Remind people" }).click();
  const results = page.getByRole("list", { name: "Reminder delivery" });
  await expect(results).toContainText("Chen: in-app queued");
  await expect(results).toContainText("Chen: email skipped (email is not configured)"); // never claims it was sent
  await expect(results).toContainText("Maya: email skipped (no email address given)");
  expect(await page.locator("body").innerText()).not.toContain("chen.sentinel"); // the address never comes back

  await expect(chen.getByRole("alert").filter({ hasText: "your private answer is still needed" })).toBeVisible({ timeout: 10_000 });
  const wcag = (p: Page) => new AxeBuilder({ page: p }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect((await wcag(chen)).violations).toEqual([]); // banner + notify button
  expect((await wcag(page)).violations).toEqual([]); // delivery list
  const notes = await chen.evaluate(() => (window as unknown as { __notes: { title: string; body: string }[] }).__notes);
  expect(notes.length).toBe(1);
  expect(notes[0].body).toContain("still needed");
  expect(notes[0].body).not.toMatch(/\d{2,}|Maya|Ben/); // no numbers, no one else's name

  // A second nudge right away is rate-limited, and the page doesn't notify twice
  await page.getByRole("button", { name: "Remind people" }).click();
  await expect(page.getByText("Nobody needed a new reminder yet.")).toBeVisible();
  await chen.waitForTimeout(3500);
  expect((await chen.evaluate(() => (window as unknown as { __notes: unknown[] }).__notes)).length).toBe(1);

  // Answering clears the reminder
  await chen.getByLabel("Hours per week you can give").fill("6");
  await chen.getByLabel("Dollars per month you can put in").fill("400");
  await chen.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await chen.getByRole("button", { name: "Save my private answer" }).click();
  await expect(chen.getByText(/Saved\. Waiting for the others/)).toBeVisible();
  await expect(chen.getByText(/Reminder:/)).toHaveCount(0);
});

test("scheduler sends the first reminder by itself, with nobody clicking anything", async ({ page, context }) => {
  await page.goto("/?tab=decisions");
  await page.getByLabel(/Short 45-second deadline/).check();
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByRole("button", { name: /^Chen/ }).click();
  const chen = await openChen(page, context);

  // first reminder is due half-way (about 22 s); the scheduler ticks every 2 s in this test server
  await expect(chen.getByRole("alert").filter({ hasText: "Reminder:" })).toBeVisible({ timeout: 40_000 });
  await page.getByText("What happened so far").click();
  const trail = await page.getByRole("list", { name: "Audit trail" }).innerText();
  expect(trail).toMatch(/reminder sent, Chen \(first: in_app queued, email skipped\)/);
  expect(trail).not.toMatch(/@/);
});

test("share invite uses the device share sheet with no private values", async ({ page }) => {
  await page.addInitScript(() => {
    const shared: unknown[] = [];
    (window as unknown as { __shared: unknown[] }).__shared = shared;
    Object.defineProperty(navigator, "share", { value: (d: unknown) => { shared.push(d); return Promise.resolve(); }, configurable: true });
  });
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByRole("button", { name: /^Chen/ }).click();
  await page.getByRole("button", { name: "Share invite" }).click();
  await expect(page.getByText("Invite ready to send.")).toBeVisible();
  const [payload] = await page.evaluate(() => (window as unknown as { __shared: { text: string; url: string }[] }).__shared);
  expect(payload.url).toMatch(/\/r\/[\w.-]+$/);
  expect(payload.text).toContain("Chen");
  expect(payload.text).not.toMatch(/\d|Maya|Ben/);
});
