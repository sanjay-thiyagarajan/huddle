import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const wcag = (p: Page) => new AxeBuilder({ page: p }).withTags(["wcag2a", "wcag2aa"]).analyze();

async function createAndPlan(page: Page) {
  await page.goto("/?tab=chores");
  await page.getByRole("button", { name: "Create the household" }).click();
  await page.getByRole("button", { name: "Add a starter set of chores" }).click();
  await page.getByRole("button", { name: "Plan the week" }).click();
  await expect(page.getByRole("table", { name: "This week's chores and who owns them" })).toBeVisible();
}
const as = async (page: Page, name: string) => {
  await page.getByRole("group", { name: "Whose private panels to show" }).getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole("heading", { name: `Your week, ${name}` })).toBeVisible(); // wait for their panel to load
};
const say = async (page: Page, words: string) => {
  await page.getByLabel("Say or type").fill(words);
  await page.getByRole("button", { name: "Send", exact: true }).click();
};
const caption = (page: Page) => page.getByRole("log", { name: "What the agent says" });
const planRows = (page: Page) => page.getByRole("table", { name: "This week's chores and who owns them" }).locator("tbody tr");

test("a household is planned fairly and each member's private limits stay private", async ({ page }) => {
  await createAndPlan(page);
  const rows = planRows(page);
  expect(await rows.count()).toBe(7);
  for (let i = 0; i < 7; i++) expect(await rows.nth(i).locator("td").nth(2).innerText()).not.toBe("Not yet"); // owners
  await expect(page.getByText(/within [\d.]+% of a fair share/)).toBeVisible();
  await expect(page.getByText(/changed hands/)).toHaveCount(0); // nothing to rotate from in the first week

  // Maya sets private limits with distinctive values
  await page.getByLabel("Hours of chores you can take this week").fill("5.3");
  await page.getByText("Preferences and skills").click();
  await page.getByLabel("How you feel about Cooking").selectOption("love");
  await page.getByLabel("Things you know how to do").fill("sentinelplumbing");
  await page.getByRole("button", { name: "Save my limits" }).click();
  await expect(page.getByText("Saved. Only you can see this.")).toBeVisible();

  // Switching to Ben shows Ben's own defaults, and nothing of Maya's anywhere on the page
  await as(page, "Ben");
  await expect(page.getByRole("heading", { name: "Your week, Ben" })).toBeVisible();
  await expect(page.getByLabel("Hours of chores you can take this week")).toHaveValue("4");
  expect(await page.locator("body").innerText()).not.toContain("sentinelplumbing");
  await page.getByText("Preferences and skills").click();
  await expect(page.getByLabel("How you feel about Cooking")).toHaveValue("ok");
  await expect(page.getByLabel("Things you know how to do")).toHaveValue("");
});

test("an ad hoc chore by words is offered to one person; accepting makes it public, and nobody can tell who was asked", async ({ page }) => {
  await createAndPlan(page);
  await say(page, "add fix the squeaky door");
  await expect(caption(page)).toContainText("Added 'Fix the squeaky door'");
  const row = planRows(page).filter({ hasText: "Fix the squeaky door" });
  await expect(row).toContainText("Being offered");
  await expect(row.locator("td").nth(2)).toHaveText("Not yet"); // no owner, no name

  // exactly one member has a request waiting
  const waiting: string[] = [];
  for (const n of ["Maya", "Ben", "Chen"]) {
    await as(page, n);
    if (await page.getByRole("region", { name: "Requests waiting for you" }).count()) waiting.push(n);
  }
  expect(waiting.length).toBe(1);
  await as(page, waiting[0]);
  const region = page.getByRole("region", { name: "Requests waiting for you" });
  await expect(region).toContainText("Nobody else can see who was asked");
  await region.getByRole("button", { name: "Accept" }).click();
  await expect(planRows(page).filter({ hasText: "Fix the squeaky door" })).toContainText(waiting[0]);
  await expect(planRows(page).filter({ hasText: "Fix the squeaky door" })).toContainText("Planned");
});

test("declining passes the request on privately; if nobody can, the group is told it needs a decision", async ({ page }) => {
  await createAndPlan(page);
  await say(page, "add fix the squeaky door");
  const seen = new Set<string>();
  for (let round = 0; round < 3; round++) {
    let asked: string | null = null;
    for (const n of ["Maya", "Ben", "Chen"]) {
      await as(page, n);
      if (await page.getByRole("region", { name: "Requests waiting for you" }).count()) asked = n;
    }
    if (!asked) break;
    seen.add(asked);
    await as(page, asked);
    const region = page.getByRole("region", { name: "Requests waiting for you" });
    await region.getByLabel("Or decline because").selectOption("prefer_not");
    await region.getByRole("button", { name: "Decline" }).click();
    await expect(region).toHaveCount(0);
  }
  expect(seen.size).toBe(3); // each person was asked once and never twice
  await expect(page.getByText(/Needs a decision from the group: Fix the squeaky door/)).toBeVisible();
  const trail = page.getByText("What happened so far");
  await trail.click();
  const text = await page.getByRole("list", { name: "Household activity" }).innerText();
  expect(text).not.toMatch(/prefer_not|prefer not/);
  expect(text).toMatch(/needs attention/);
});

test("the agent answers plain-words questions and never mentions private preferences", async ({ page }) => {
  await createAndPlan(page);
  await page.getByLabel("Hours of chores you can take this week").fill("5.3");
  await page.getByText("Preferences and skills").click();
  await page.getByLabel("Things you know how to do").fill("sentinelplumbing");
  await page.getByRole("button", { name: "Save my limits" }).click();
  const owner = (await planRows(page).filter({ hasText: "Take out the bins" }).locator("td").nth(2).innerText()).trim();

  await as(page, "Ben");
  await say(page, "who has the bins");
  await expect(caption(page)).toContainText(`${owner} has 'Take out the bins'.`);
  await say(page, "what's the plan");
  await expect(caption(page)).toContainText("fair share");
  await as(page, owner);
  await say(page, "I did the bins");
  await expect(caption(page)).toContainText("marked 'Take out the bins' done");
  await expect(planRows(page).filter({ hasText: "Take out the bins" })).toContainText("Done");
  await say(page, "sing me a song");
  await expect(caption(page)).toContainText("I can add a chore");
  const everything = await page.locator("body").innerText();
  expect(everything.split("Your private limits")[0]).not.toContain("sentinelplumbing"); // never in the shared parts
});

test("a chore with a future due date is held until its week; a member's own phone page works", async ({ page, context }) => {
  await createAndPlan(page);
  await page.getByText("Add a chore with details").click();
  await page.getByLabel("Title").fill("Clear out the attic");
  await page.getByLabel("Due date").fill("2026-12-20");
  await page.getByRole("button", { name: "Add with details" }).click();
  await expect(page.getByText(/It will be in the plan when the week is planned/)).toBeVisible();
  await expect(planRows(page).filter({ hasText: "Clear out the attic" })).toHaveCount(0);

  // Ben's private page on his phone, from his link
  const token = await page.evaluate(() => JSON.parse(localStorage.getItem("huddle-household-v1")!).members[1].token);
  const phone = await context.newPage();
  await phone.goto(`/h/${token}`);
  await expect(phone.getByRole("heading", { name: "Your household, privately" })).toBeVisible();
  await expect(phone.getByRole("heading", { name: "Your week, Ben" })).toBeVisible();
  await expect(phone.getByText(/Showing .* private panels/)).toHaveCount(0); // no shared-screen warning on his own phone
  await phone.getByLabel("Hours of chores you can take this week").fill("6");
  await phone.getByRole("button", { name: "Save my limits" }).click();
  await expect(phone.getByText("Saved. Only you can see this.")).toBeVisible();
});

test("handing a chore back asks someone else, and the household survives a reload", async ({ page }) => {
  await createAndPlan(page);
  await as(page, "Maya");
  const mine = page.locator(".mine li").first();
  const title = (await mine.locator("strong").innerText()).trim();
  await mine.getByRole("button", { name: "Hand back" }).click();
  await expect(planRows(page).filter({ hasText: title })).toContainText("Being offered");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Our home" })).toBeVisible(); // stored on this device
  await page.getByRole("button", { name: "Forget this household on this device" }).click();
  await expect(page.getByRole("heading", { name: "Share the household load" })).toBeVisible();
});

test("household pages have no accessibility violations in light and dark, and fit a phone", async ({ page }) => {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/?tab=chores");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    expect((await wcag(page)).violations, `setup ${scheme}`).toEqual([]);
    await createAndPlan(page);
    await page.getByText("Preferences and skills").click();
    await say(page, "add fix the squeaky door");
    await expect(caption(page)).toContainText("Added");
    expect((await wcag(page)).violations, `household ${scheme}`).toEqual([]);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  expect((await wcag(page)).violations).toEqual([]);
});
