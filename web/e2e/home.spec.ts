import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const wcag = (p: Page) => new AxeBuilder({ page: p }).withTags(["wcag2a", "wcag2aa"]).analyze();
const as = async (page: Page, name: string) => {
  await page.getByRole("group", { name: "Whose private panels to show" }).getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole("heading", { name: `Your week, ${name}` })).toBeVisible();
};
async function answerCare(page: Page, hours: string, dollars: string, ...chips: string[]) {
  const card = page.getByRole("region", { name: /Decision: sharing a parent's care/ });
  await card.getByLabel("Hours per week you can give").fill(hours);
  await card.getByLabel("Dollars per month you can put in").fill(dollars);
  for (const c of chips) await card.getByRole("button", { name: c }).click();
  await card.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await card.getByRole("button", { name: "Save my private answer" }).click();
}

test("one home: chores and a care decision for the same people, with care counted in the chore plan", async ({ page }) => {
  await page.goto("/?tab=home");
  await page.getByRole("button", { name: "Create the household" }).click();
  await page.getByRole("button", { name: "Add a starter set of chores" }).click();
  await expect(page.getByText("Family decisions")).toBeVisible();

  // start a care decision for the household: nobody retypes who is in it
  await page.getByRole("button", { name: "Share a parent's care" }).click();
  await expect(page.getByText(/Huddle doesn't hire or pay anyone/)).toBeVisible();
  await expect(page.getByText(/suggests paid help as one option/)).toBeVisible();
  await page.getByRole("button", { name: "Ask everyone privately" }).click();
  await expect(page.getByRole("list", { name: "Open decisions" })).toContainText("0 of 3 have answered");

  await answerCare(page, "13.5", "437");  // Maya, with distinctive private values
  await expect(page.getByText(/Your answer is saved and private\. 1 of 3 have answered/)).toBeVisible();
  await as(page, "Ben");
  await answerCare(page, "8", "500", "I live far away");
  await as(page, "Chen");
  await answerCare(page, "6", "400", "Driving and transport");

  // the decision closes for everyone: Chen sees the plan, his own private share, and the check-in
  const card = page.getByRole("region", { name: /Decision: sharing a parent's care/ });
  await expect(card.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible({ timeout: 15_000 });
  await expect(card.locator(".myshare")).toContainText("Your part, Chen");
  await expect(card.getByRole("heading", { name: /the day after/i })).toBeVisible();
  await expect(page.getByRole("list", { name: "Family plans so far" })).toContainText("Care plan");

  // Ben never sees Maya's private hours or dollars anywhere on his page
  await as(page, "Ben");
  const bens = await page.locator("body").innerText();
  expect(bens).not.toContain("13.5");
  expect(bens).not.toContain("437");

  // plan the week: the care people have taken on counts in the chore plan
  await page.getByRole("button", { name: "Plan the week" }).click();
  await expect(page.getByText(/Care already taken on is counted in everyone's share/)).toBeVisible();
  let found = 0;
  for (const n of ["Maya", "Ben", "Chen"]) {
    await as(page, n);
    if (await page.getByText(/of care you've taken on/).count()) found++;
  }
  expect(found).toBeGreaterThanOrEqual(1);
});

test("the home pages have no accessibility violations with decisions in play, in light and dark", async ({ page }) => {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/?tab=home");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.getByRole("button", { name: "Create the household" }).click();
    await page.getByRole("button", { name: "Plan a weekend" }).click();
    await expect(page.getByRole("region", { name: /Decision: a weekend plan/ })).toBeVisible();
    expect((await wcag(page)).violations, `open decision ${scheme}`).toEqual([]);
  }
});

test("a weekend decision started from the home shows on another member's own phone page, with their own form", async ({ page, context }) => {
  await page.goto("/?tab=home");
  await page.getByRole("button", { name: "Create the household" }).click();
  await page.getByRole("button", { name: "Plan a weekend" }).click();
  const card = page.getByRole("region", { name: /Decision: a weekend plan/ });
  await card.getByLabel(/Most you'd spend per person/).fill("90");
  await card.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await card.getByRole("button", { name: "Save my private answer" }).click();
  await expect(page.getByRole("list", { name: "Open decisions" })).toContainText("1 of 3 have answered");

  // another member's own phone page shows the same decision, with their own answer form
  const token = await page.evaluate(() => JSON.parse(localStorage.getItem("huddle-household-v1")!).members[1].token);
  const phone = await context.newPage();
  await phone.goto(`/h/${token}`);
  const theirs = phone.getByRole("region", { name: /Decision: a weekend plan/ });
  await expect(theirs.getByLabel(/Most you'd spend per person/)).toBeVisible();
  await expect(theirs).not.toContainText("90"); // Maya's private budget is nowhere on Ben's page
});
