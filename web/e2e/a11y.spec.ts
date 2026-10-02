import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function audit(page: import("@playwright/test").Page, label: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const summary = violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
  expect(summary, `${label}: axe violations`).toEqual([]);
}

for (const scheme of ["light", "dark"] as const) {
  test(`accessibility (${scheme}): start, answer, reveal, link page`, async ({ page, context }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/");
    await audit(page, "start screen");

    await page.getByRole("button", { name: "Share care for a parent" }).click();
    await page.getByRole("button", { name: "Start the huddle" }).click();
    await expect(page.getByLabel("Hours per week you can give")).toBeVisible();
    await page.getByLabel("Show what the server holds").check();
    await audit(page, "answer panel");

    await page.getByRole("button", { name: "Chen" }).click();
    const link = (await page.locator(".linkbox code").innerText()).trim();
    const phone = await context.newPage();
    await phone.emulateMedia({ colorScheme: scheme });
    await phone.goto(link);
    await expect(phone.getByRole("heading", { name: /Hi Chen/ })).toBeVisible();
    await audit(phone, "link page");

    await page.getByRole("button", { name: "Close now" }).click();
    await expect(page.getByRole("heading", { name: /care plan/ })).toBeVisible();
    await audit(page, "reveal");
  });
}
