import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const consent = (p: Page) => p.getByRole("checkbox", { name: /I'm an adult/ }).check();
const save = (p: Page) => p.getByRole("button", { name: "Save my private answer" }).click();

test("care need editor changes what the plan needs", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Sharing care for a parent" }).click();
  await page.getByText(/What the care plan needs/).click();
  await page.getByLabel("Task 3 hours per week").fill("2"); // meals 8 -> 2: total 24
  await page.getByLabel("Money needed per month (dollars)").fill("1500");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByRole("button", { name: "Close now" }).click();
  await expect(page.getByText(/The plan needs 24 h\/week and \$1,500\/month/)).toBeVisible();
});

test("trip round: remote link, reveal, explain, check-in summary and audit trail", async ({ page, context }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "A trip with friends" }).click();
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
    await expect(p.getByText(/At least one person is not comfortable/)).toBeVisible({ timeout: 10_000 });
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
  await page.goto("/");
  await page.getByRole("button", { name: "Sharing care for a parent" }).click();
  await page.getByText(/What the care plan needs/).click();
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await expect(page.getByLabel("Hours per week you can give")).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});
