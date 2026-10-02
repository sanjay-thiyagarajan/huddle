import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const say = async (p: Page, words: string) => {
  await p.getByLabel(/Say it \(typed here/).fill(words);
  await p.getByRole("button", { name: "Send", exact: true }).click();
};

test("voice-only: private by default, never echoes a value, hands off to phone or screen", async ({ page, context }) => {
  // Record what would be spoken aloud, so we can assert on it
  await page.addInitScript(() => {
    const spoken: string[] = [];
    (window as unknown as { __spoken: string[] }).__spoken = spoken;
    Object.defineProperty(window, "speechSynthesis", {
      value: { speak: (u: { text: string }) => spoken.push(u.text), cancel: () => undefined }, configurable: true,
    });
    (window as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance =
      class { text: string; constructor(t: string) { this.text = t; } };
  });
  await page.goto("/");
  await page.getByLabel("How Chen answers").selectOption("voice");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByLabel("Voice-only mode (like a speaker with no screen)").check();
  const captions = page.getByRole("log", { name: "What the assistant says" });

  // ---- Maya: alone, answers by voice -------------------------------------------------------------
  await page.getByRole("button", { name: /Start voice session for Maya/ }).click();
  await expect(captions).toContainText("is anyone close enough to hear you");
  await say(page, "just me");
  await expect(captions).toContainText("Do you agree to answer?");
  await say(page, "yes I agree");
  await expect(captions).toContainText("how many hours a week");
  await say(page, "I can do maybe twelve hours but not nights");
  await expect(captions).toContainText("how many dollars a month"); // one follow-up for the missing field
  await say(page, "about six hundred dollars a month");
  await expect(captions).toContainText("Say save it to keep it");
  await say(page, "save it");
  await expect(page.getByText("Maya's answer is saved")).toBeVisible();

  // Nothing the person said, and no number, appears on screen or in the spoken replies
  const screen = (await page.locator("main").innerText()).toLowerCase();
  for (const secret of ["twelve", "six hundred", "600", "overnight"]) expect(screen).not.toContain(secret);
  const spoken = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
  expect(spoken.length).toBeGreaterThan(4);
  expect(spoken.join(" ")).not.toMatch(/\d/);
  expect(spoken.join(" ").toLowerCase()).not.toMatch(/twelve|six hundred|night/);

  // ---- Ben: someone is nearby, so the assistant offers his phone instead ---------------------------
  await page.getByRole("button", { name: /^Ben/ }).click();
  await page.getByRole("button", { name: /Start voice session for Ben/ }).click();
  await say(page, "yes my sister is right here");
  await expect(captions).toContainText("send me a link");
  await say(page, "send me a link");
  const linkBox = page.locator(".linkbox");
  await expect(linkBox).toContainText("so nobody hears it");
  const link = (await linkBox.locator("code").innerText()).trim();
  const phone = await context.newPage();
  await phone.goto(link);
  await phone.getByLabel("Hours per week you can give").fill("8");
  await phone.getByLabel("Dollars per month you can put in").fill("500");
  await phone.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await phone.getByRole("button", { name: "Save my private answer" }).click();
  await expect(phone.getByText(/Saved\. Waiting for the others/)).toBeVisible();

  // ---- Chen: prefers the screen ------------------------------------------------------------------
  await page.getByRole("button", { name: /^Chen/ }).click();
  await page.getByRole("button", { name: /Start voice session for Chen/ }).click();
  await say(page, "just me");
  await say(page, "actually use the screen");
  await expect(page.getByLabel("Hours per week you can give")).toBeVisible(); // the on-screen form took over
  await page.getByLabel("Hours per week you can give").fill("6");
  await page.getByLabel("Dollars per month you can put in").fill("400");
  await page.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await page.getByRole("button", { name: "Save my private answer" }).click();
  await expect(page.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible({ timeout: 10_000 });
});

test("voice-only view has no accessibility violations and honours read-back only on request", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Plan a weekend" }).click();
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByLabel("Voice-only mode (like a speaker with no screen)").check();
  await page.getByRole("button", { name: /Start voice session for Maya/ }).click();
  const captions = page.getByRole("log", { name: "What the assistant says" });
  await say(page, "just me"); await say(page, "yes");
  await say(page, "under 75 dollars and no crowds");
  await expect(captions).toContainText("Say save it to keep it");
  expect(await captions.innerText()).not.toMatch(/75|crowds/);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);

  await say(page, "read it back"); // explicit opt-in
  await expect(captions).toContainText("You said at most 75 dollars");
  await expect(captions.locator(".caption.warn")).toHaveCount(1); // flagged as having spoken values
});
