import { expect, test } from "@playwright/test";

// Distinctive values: nobody but their owner should ever see these.
const MAYA = "I can do maybe twelve hours and $613 a month but not nights";

test("care round: voice, remote link and reveal, with no value leaking into other panels", async ({ page, context }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Share care for a parent" }).click();
  await page.getByRole("button", { name: "Start the huddle" }).click();

  // Maya, by voice (typed fallback), via the agent parser
  await page.getByLabel("Say it in your own words, Maya").fill(MAYA);
  await page.getByRole("button", { name: "Fill in from what I said" }).click();
  await expect(page.getByLabel("Hours per week you can give")).toHaveValue("12");
  await expect(page.getByLabel("Dollars per month you can put in")).toHaveValue("613");
  await page.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await page.getByRole("button", { name: "Save my private answer" }).click();
  await expect(page.getByText("Maya's answer is saved")).toBeVisible();

  // Switching to Ben: Maya's numbers are nowhere on screen, and the debug panel shows no values
  await page.getByRole("button", { name: "Ben" }).click();
  await page.getByLabel("Show what the server holds").check();
  await expect(page.getByRole("list", { name: "What the server holds" })).toContainText("Maya: answer stored");
  expect(await page.locator("body").innerText()).not.toContain("613");

  await page.getByLabel("Hours per week you can give").fill("8");
  await page.getByLabel("Dollars per month you can put in").fill("500");
  await page.getByRole("button", { name: "I live far away" }).click();
  await page.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await page.getByRole("button", { name: "Save my private answer" }).click();
  await expect(page.getByText("Ben's answer is saved")).toBeVisible();

  // Chen answers on his own page from the private link
  await page.getByRole("button", { name: "Chen" }).click();
  const link = (await page.locator(".linkbox code").innerText()).trim();
  const phone = await context.newPage();
  await phone.goto(link);
  await expect(phone.getByRole("heading", { name: /Hi Chen/ })).toBeVisible();
  await phone.getByLabel("Hours per week you can give").fill("6");
  await phone.getByLabel("Dollars per month you can put in").fill("400");
  await phone.getByRole("button", { name: "Driving and transport" }).click();
  await phone.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await phone.getByRole("button", { name: "Save my private answer" }).click();

  // Everyone answered: both screens reveal the same aggregate
  for (const p of [page, phone]) {
    await expect(p.getByRole("heading", { name: /care plan that fits everyone/ })).toBeVisible({ timeout: 10_000 });
    await expect(p.getByText(/never shown or attributed/)).toBeVisible();
    await expect(p.locator(".reveal").getByText("Decision aid, not medical, legal or financial advice.")).toBeVisible();
    await expect(p.getByText(/hint at what a person is able to do/)).toBeVisible();
    expect(await p.locator("body").innerText()).not.toContain("613");
  }
});

test("failure path: reminder fires, then defaults are applied and stated", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Plan a weekend" }).click();
  await page.getByLabel(/Short 45-second deadline/).check();
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByLabel("Most you'd spend per person (dollars)").fill("80");
  await page.getByRole("checkbox", { name: /I'm an adult/ }).check();
  await page.getByRole("button", { name: "Save my private answer" }).click();

  await expect(page.getByText(/A reminder went out/)).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText(/did not answer, so a middle-of-the-road default/)).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText(/With two people, the other person may be able to infer your number/)).toBeVisible();
});
