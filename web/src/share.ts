/** Send text/URL with the device's own share sheet when there is one; otherwise copy it. Nothing goes
 *  through our server, and no contact details are stored. Returns what happened, for the UI to say. */
export async function shareOrCopy(data: { title: string; text: string; url: string }): Promise<"shared" | "copied" | "failed"> {
  try {
    if (typeof navigator.share === "function") { await navigator.share(data); return "shared"; }
    await navigator.clipboard.writeText(`${data.text}\n${data.url}`);
    return "copied";
  } catch (e) {
    return (e as Error).name === "AbortError" ? "shared" : "failed"; // closing the share sheet is not an error
  }
}

export const inviteText = (name: string) =>
  `${name}, I'd like your private answer for our group decision. It takes about two minutes and nobody else sees it.`;
