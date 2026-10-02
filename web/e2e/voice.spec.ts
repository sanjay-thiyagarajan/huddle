import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

// Microphone path with Chrome's fake audio device playing a SYNTHETIC voice clip (macOS `say`).
// Needs the `voice` extra (torch), so it runs only when HUDDLE_E2E_VOICE=1; the default CI image skips it.
test.skip(!process.env.HUDDLE_E2E_VOICE, "set HUDDLE_E2E_VOICE=1 with the voice extra installed");

const clip = fileURLToPath(new URL("../../tests/audio/test/samantha/t1.wav", import.meta.url));
test.use({
  permissions: ["microphone"],
  launchOptions: {
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${clip}`],
  },
});

test("enrol Maya from the mic, then recognise her", async ({ page }) => {
  await page.goto("/?tab=decisions");
  await page.getByRole("button", { name: "Start the huddle" }).click();
  await page.getByText("Voice recognition setup").click();
  await page.getByRole("button", { name: "Enrol Maya" }).click();
  await expect(page.getByText(/Maya's voice profile is saved/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Ben", exact: true }).click(); // switch away, then recognise
  await page.getByRole("button", { name: "Who's speaking? Listen" }).click();
  await expect(page.getByText("Recognized Maya.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Recognized: Maya/)).toBeVisible();
});
