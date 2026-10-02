import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const consent = (p: Page) => p.getByRole("checkbox", { name: /I'm an adult/ }).check();
const save = (p: Page) => p.getByRole("button", { name: "Save my private answer" }).click();

test("care need editor changes what the plan needs", async ({ page }) => {
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Share care for a parent" }).click();
  await page.getByText(/What the care plan needs/).click();
  await page.getByLabel("Task 3 hours per week").fill("2"); // meals 8 -> 2: total 24
  await page.getByLabel("Money needed per month (dollars)").fill("1500");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByRole("button", { name: "Close now" }).click();
  await expect(page.locator(".lead")).toContainText(/The plan needs 24 h\/week and \$1,500\/month/);
});

test("trip round: remote link, reveal, explain, check-in summary and audit trail", async ({ page, context }) => {
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Plan a trip" }).click();
  await page.getByRole("button", { name: "Start the huddle" }).click();

  // Maya: $400, beach, no flying
  await page.getByLabel(/Most you'd spend per person for the whole trip/).fill("400");
  await page.getByRole("button", { name: "Beach" }).click();
  await page.getByRole("button", { name: "Flying" }).click();
  await consent(page); await save(page);
  await expect(page.getByText("Maya's answer is saved")).toBeVisible();
  // Ben: $900, food
  await page.getByRole("button", { name: /^Ben/ }).click();
  await page.getByLabel(/Most you'd spend per person for the whole trip/).fill("900");
  await page.getByRole("button", { name: "Food-focused" }).click();
  await consent(page); await save(page);
  await expect(page.getByText("Ben's answer is saved")).toBeVisible();
  // Chen on the private link: $350, relaxed, no camping
  await page.getByRole("button", { name: /^Chen/ }).click();
  const link = (await page.locator(".linkbox code").innerText()).trim();
  const phone = await context.newPage();
  await phone.goto(link);
  await phone.getByLabel(/Most you'd spend per person for the whole trip/).fill("350");
  await phone.getByRole("button", { name: "Relaxed" }).click();
  await phone.getByRole("button", { name: "Camping" }).click();
  await consent(phone); await save(phone);

  await expect(page.getByRole("heading", { name: /trip that works for the group/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".plan strong")).toHaveText("Beach house on the coast");

  await page.getByRole("button", { name: "Explain this in plain words" }).click();
  await expect(page.getByText(/built-in explainer/)).toBeVisible();

  // Check-in: summary stays hidden until all three have answered, then is unattributed
  const who = page.getByRole("group", { name: "Who is checking in" });
  await who.getByRole("button", { name: "Maya" }).click();
  await page.getByRole("button", { name: /4\. Comfortable/ }).click();
  await expect(page.getByText(/1 of 3 have checked in/)).toBeVisible();
  await who.getByRole("button", { name: "Ben" }).click();
  await page.getByRole("button", { name: /5\. Very comfortable/ }).click();
  await expect(phone.getByRole("heading", { name: /the day after/i })).toBeVisible({ timeout: 10_000 });
  await phone.getByRole("button", { name: /2\. Uneasy/ }).click();
  for (const p of [page, phone]) {
    await expect(p.locator(".checkin").getByText(/At least one person is not comfortable/)).toBeVisible({ timeout: 10_000 });
    const text = await p.locator("body").innerText();
    expect(text).not.toMatch(/Chen.{0,40}Uneasy|Uneasy.{0,40}Chen/s);
  }

  // Audit trail lists who did what, never values
  await page.getByText("What happened so far").click();
  const trail = await page.getByRole("list", { name: "Audit trail" }).innerText();
  expect(trail).toMatch(/answered, Maya/);
  expect(trail).toMatch(/closed/);
  expect(trail).not.toMatch(/400|900|350/);
});

test("phone width: no horizontal scroll and no accessibility violations", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Share care for a parent" }).click();
  await page.getByText(/What the care plan needs/).click();
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await expect(page.getByLabel("Hours per week you can give")).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

// ---- change answer, revisit + fairness, plan card ----------------------------------------------

async function careAnswer(p: Page, hours: string, dollars: string, ...chips: string[]) {
  await p.getByLabel("Hours per week you can give").fill(hours);
  await p.getByLabel("Dollars per month you can put in").fill(dollars);
  for (const c of chips) await p.getByRole("button", { name: c }).click();
  await consent(p); await save(p);
}

test("change my answer until the round closes; the audit trail shows a revision without a name", async ({ page }) => {
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Plan a weekend" }).click();
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByLabel(/Most you'd spend per person/).fill("100");
  await consent(page); await save(page);
  await expect(page.getByText("Maya's answer is saved")).toBeVisible();

  await page.getByRole("button", { name: "Change my answer" }).click();
  await expect(page.getByLabel(/Most you'd spend per person/)).toHaveValue("100"); // prefilled with their own answer
  await page.getByLabel(/Most you'd spend per person/).fill("300");
  await page.getByRole("button", { name: "Update my private answer" }).click();
  await expect(page.getByText("Maya's answer is saved")).toBeVisible();
  await page.getByRole("button", { name: "Change my answer" }).click();
  await expect(page.getByLabel(/Most you'd spend per person/)).toHaveValue("300");

  // Switching profile must not carry Maya's draft into Ben's panel
  await page.getByRole("button", { name: /^Ben/ }).click();
  await expect(page.getByLabel(/Most you'd spend per person/)).toHaveValue("");
  await page.getByText("What happened so far").click();
  const trail = await page.getByRole("list", { name: "Audit trail" }).innerText();
  expect(trail).toMatch(/revised/);
  expect(trail).not.toMatch(/revised, /); // no actor is attached to a revision
  expect(trail).not.toMatch(/\b(100|300)\b/);
});

test("next round keeps the group, starts fresh, and shows the fair-share record", async ({ page }) => {
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Share care for a parent" }).click();
  await page.getByLabel("How Chen answers").selectOption("voice"); // answer all three at the device
  await page.getByRole("button", { name: "Start the huddle" }).click();

  const round = async (a: [string, string], b: [string, string], c: [string, string]) => {
    await careAnswer(page, a[0], a[1], "Overnight cover");
    await page.getByRole("button", { name: /^Ben/ }).click();
    await careAnswer(page, b[0], b[1]);
    await page.getByRole("button", { name: /^Chen/ }).click();
    await careAnswer(page, c[0], c[1]);
  };
  await round(["12", "600"], ["8", "500"], ["6", "400"]);
  await expect(page.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Fair share over time")).toHaveCount(0); // no history yet

  await page.getByRole("button", { name: "Start the next round" }).click();
  await expect(page.getByText(/A new round is open for the same people/)).toBeVisible();
  await expect(page.getByLabel("Hours per week you can give")).toHaveValue(""); // nothing carried over
  await round(["12", "600"], ["8", "500"], ["6", "400"]);
  await expect(page.getByText("Fair share over time")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/across 2 plans/)).toBeVisible();
  await expect(page.getByText(/never anyone's hours or private limits/)).toBeVisible();
});

test("plan card: copy, read aloud and print contain only the aggregate", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.addInitScript(() => { // deterministic speech: record what would be spoken
    const spoken: string[] = [];
    (window as unknown as { __spoken: string[] }).__spoken = spoken;
    Object.defineProperty(window, "speechSynthesis", {
      value: { speak: (u: { text: string }) => spoken.push(u.text), cancel: () => undefined }, configurable: true,
    });
    (window as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class { text: string; onend = null; onerror = null; constructor(t: string) { this.text = t; } };
  });
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Share care for a parent" }).click();
  await page.getByLabel("How Chen answers").selectOption("voice");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await careAnswer(page, "13.5", "437", "Overnight cover");
  await page.getByRole("button", { name: /^Ben/ }).click();
  await careAnswer(page, "17.5", "613");
  await page.getByRole("button", { name: /^Chen/ }).click();
  await careAnswer(page, "11.5", "829");
  await expect(page.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible({ timeout: 10_000 });

  await page.getByRole("button", { name: "Copy plan card" }).click();
  await expect(page.getByRole("button", { name: "Plan card copied" })).toBeVisible();
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  expect(clip).toContain("Care plan");
  expect(clip).toContain("not medical, legal or financial advice");
  for (const secret of ["13.5", "17.5", "11.5", "437", "613", "829"]) expect(clip).not.toContain(secret);

  await page.getByRole("button", { name: "Read it aloud" }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.length)).toBe(1);
  const spoken = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken[0]);
  expect(spoken).toContain("Care plan");
  for (const secret of ["13.5", "437", "613"]) expect(spoken).not.toContain(secret);

  await page.emulateMedia({ media: "print" }); // print view hides the controls and the device column
  await expect(page.getByRole("button", { name: "Copy plan card" })).toBeHidden();
  await expect(page.locator(".device")).toBeHidden();
  await expect(page.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible();
  await page.emulateMedia({ media: "screen" });
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

test("one household: care plan, then a weekend for the same family with a private care-load hint", async ({ page }) => {
  await page.goto("/?tab=decisions");
  await page.getByLabel("How Chen answers").selectOption("voice");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await expect(page.locator(".hint")).toHaveCount(0); // no hints inside the care round itself

  await careAnswer(page, "12", "600");
  await page.getByRole("button", { name: /^Ben/ }).click();
  await careAnswer(page, "8", "500");
  await page.getByRole("button", { name: /^Chen/ }).click();
  await careAnswer(page, "0", "400"); // Chen can give no hours, so carries no heavy tasks
  await expect(page.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible({ timeout: 10_000 });

  // Same family, different decision: no retyping of people
  await expect(page.getByRole("heading", { name: "What should the family decide next?" })).toBeVisible();
  await page.getByRole("button", { name: "Plan a weekend", exact: true }).click();
  await expect(page.getByText(/The next decision is open for the same family/)).toBeVisible();
  await expect(page.getByLabel(/Most you'd spend per person/)).toBeVisible();

  // Maya carries heavy tasks: she gets an optional private hint; applying it is her choice
  await page.getByRole("button", { name: /^Maya/ }).click();
  const hint = page.locator(".hint");
  await expect(hint).toContainText(/In your household's latest care plan you carry \d+ h\/week of heavy tasks/);
  await expect(hint).toContainText("only you see this");
  await page.getByRole("button", { name: "Add these to my dealbreakers" }).click();
  await expect(page.getByRole("button", { name: "Early start" })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel(/Most you'd spend per person/).fill("100");
  await consent(page); await save(page);

  // Chen carries nothing, so no hint
  await page.getByRole("button", { name: /^Chen/ }).click();
  await expect(page.locator(".hint")).toHaveCount(0);
  await page.getByLabel(/Most you'd spend per person/).fill("100");
  await consent(page); await save(page);
  await page.getByRole("button", { name: /^Ben/ }).click();
  await page.getByLabel(/Most you'd spend per person/).fill("100");
  await consent(page); await save(page);

  await expect(page.getByRole("heading", { name: "Here's the plan" })).toBeVisible({ timeout: 10_000 });
  const plans = page.getByRole("list", { name: "Family plans so far" });
  await expect(plans).toContainText("Care plan");
  await expect(plans).toContainText("Weekend plan");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

test("care plan: the group sees who owns what with no hours; each person sees only their own", async ({ page, context }) => {
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Start the huddle" }).click(); // Maya, Ben by voice; Chen by link
  await careAnswer(page, "12", "600");
  await page.getByRole("button", { name: /^Ben/ }).click();
  await careAnswer(page, "8", "500");
  await page.getByRole("button", { name: /^Chen/ }).click();
  const link = (await page.locator(".linkbox code").innerText()).trim();
  const phone = await context.newPage();
  await phone.goto(link);
  await phone.getByLabel("Hours per week you can give").fill("6");
  await phone.getByLabel("Dollars per month you can put in").fill("400");
  await consent(phone); await save(phone);

  await expect(page.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible({ timeout: 10_000 });
  // The group view: ownership only, with no per-person hours anywhere in it
  const split = page.locator(".split");
  await expect(split.getByRole("heading", { name: "Who owns what" })).toBeVisible();
  await expect(split).toContainText("Overnight cover");
  expect(await split.innerText()).not.toMatch(/\d+\s*h\/week/);

  // Each profile sees only their own hours
  const who = page.getByRole("group", { name: "Who is checking in" });
  await who.getByRole("button", { name: "Maya" }).click();
  const mine = page.locator(".myshare");
  await expect(mine.getByRole("heading", { name: "Your part, Maya" })).toBeVisible();
  await expect(mine).toContainText(/\d+ h\/week/);
  const mayaText = await mine.innerText();
  await who.getByRole("button", { name: "Ben" }).click();
  await expect(mine.getByRole("heading", { name: "Your part, Ben" })).toBeVisible();
  expect(await mine.innerText()).not.toEqual(mayaText);
  await expect(mine).toContainText("shown on a shared screen"); // honest about the shared screen

  // Chen on his phone sees his own part, privately
  const own = phone.locator(".myshare");
  await expect(own.getByRole("heading", { name: "Your part, Chen" })).toBeVisible({ timeout: 10_000 });
  await expect(own).toContainText("Overnight cover");
  await expect(own).toContainText("Only you see this");
  expect(await phone.locator(".split").innerText()).not.toMatch(/\d+\s*h\/week/);
});
