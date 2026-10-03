import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const as = async (page: Page, name: string) => {
  await page.getByRole("group", { name: "Whose private panels to show" }).getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole("heading", { name: `Your week, ${name}` }).or(page.getByRole("heading", { name: "Your week", exact: true }))).toBeVisible();
};
const myTime = (page: Page) => page.getByRole("button", { name: "My time" }).click();
const say = async (page: Page, text: string) => {
  await page.getByLabel("Say or type").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
};
const log = (page: Page) => page.getByRole("log", { name: "What the scheduling agent says" });

test("my time: private schedule, a clash settled by conversation, and find-a-time with a guest", async ({ page, browser }) => {
  await page.goto("/?tab=home");
  await page.getByRole("button", { name: "Create the household" }).click();
  await expect(page.getByText("Family decisions")).toBeVisible();
  await myTime(page);

  // add things in plain words; a clash is explained and settled by answering
  await say(page, "school concert Thursday 6pm for 90 minutes can't move");
  await expect(log(page)).toContainText("Added 'school concert'");
  await say(page, "dinner with Priya Thursday 7pm for 2 hours");
  await expect(log(page)).toContainText(/clashes with 'school concert'/);
  await expect(log(page)).toContainText(/family comes above friends|fixed/i);
  await page.getByRole("button", { name: "Yes, do that" }).click();
  await expect(log(page)).toContainText(/Moved 'dinner with Priya'/);
  // "Thursday" falls in next week unless today is Monday to Thursday
  if (![1, 2, 3, 4].includes(new Date().getDay())) await page.getByRole("button", { name: "Next week" }).click();
  const week = page.getByRole("region", { name: "Your week", exact: true });
  await expect(week).toContainText("dinner with Priya");
  await expect(week).toContainText("school concert");
  await expect(page.getByRole("region", { name: "Clashes" })).toHaveCount(0);

  // someone else in the household never sees it
  await page.getByRole("button", { name: "Chores and decisions" }).click();
  await as(page, "Ben");
  await myTime(page);
  await expect(page.getByText("Nothing yet.")).toBeVisible();
  expect(await page.locator("body").innerText()).not.toContain("school concert");

  // Maya finds a time with Ben and a guest
  await page.getByRole("button", { name: "Chores and decisions" }).click();
  await as(page, "Maya");
  await myTime(page);
  const form = page.getByRole("region").filter({ has: page.getByRole("heading", { name: "Find a time" }) });
  await form.getByLabel("What").fill("Drinks");
  await form.getByRole("button", { name: "Ben" }).click();
  await form.getByLabel(/Guests outside/).fill("Priya");
  await form.getByRole("button", { name: "Ask them" }).click();
  const links = page.getByRole("list", { name: "Guest links" });
  await expect(links).toContainText("Priya");
  const guestLink = (await links.locator("code").innerText()).trim();
  const card = page.getByRole("region", { name: "Find a time: Drinks" });
  await card.getByRole("button", { name: "Use my suggested answers" }).click();
  await expect(card).toContainText(/Your answer is saved and private/);

  // Ben answers from his own schedule; the guest answers from the link, on her own device
  await page.getByRole("button", { name: "Chores and decisions" }).click();
  await as(page, "Ben");
  await myTime(page);
  await page.getByRole("region", { name: "Find a time: Drinks" }).getByRole("button", { name: "Use my suggested answers" }).click();
  const guest = await (await browser.newContext()).newPage();
  await guest.goto(guestLink);
  await expect(guest.getByRole("heading", { name: /When can you do "Drinks"/ })).toBeVisible();
  for (const legend of await guest.locator("fieldset.chips legend").allInnerTexts()) {
    await guest.getByRole("group", { name: legend }).getByRole("button", { name: "Works" }).click();
  }
  await guest.getByRole("checkbox").check();
  await guest.getByRole("button", { name: "Save my private answer" }).click();
  await expect(guest.getByRole("heading", { name: "Here's a time that works" })).toBeVisible({ timeout: 15_000 });
  expect(await guest.locator("body").innerText()).not.toContain("school concert");

  // the chosen time lands on Maya's and Ben's weeks, and the result names nobody
  await page.getByRole("button", { name: "Chores and decisions" }).click();
  await as(page, "Maya");
  await myTime(page);
  const done = page.getByRole("region", { name: "Find a time: Drinks" });
  await expect(done).toContainText(/works|best fit|closest/i, { timeout: 15_000 });
  await expect(done).not.toContainText("Ben");
});

test("my time: rules, chore availability suggestion, and accessibility", async ({ page }) => {
  await page.goto("/?tab=home");
  await page.getByRole("button", { name: "Create the household" }).click();
  await myTime(page);
  await page.getByLabel("Most evenings out in a week (blank for no limit)").fill("2");
  await page.getByRole("button", { name: "Move Friends up" }).click();
  await page.getByRole("button", { name: "Save rules" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(page.getByRole("list", { name: "Which circle wins a clash" }).locator("li").first()).toContainText(/Family|Friends/);
  await page.getByRole("button", { name: "Use this as my chore availability" }).click();
  await expect(page.getByRole("button", { name: "Saved as your chore availability" })).toBeVisible();
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
});
