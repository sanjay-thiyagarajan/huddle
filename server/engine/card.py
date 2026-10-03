"""Plan card: a copyable, printable, speakable summary built ONLY from the aggregate result.

It takes the stored group result (already unattributed) and nothing else, so it cannot include
a private answer. Fairness and check-in lines also come from aggregate sources.
"""


def build_card(result: dict, checkin: dict | None = None) -> dict:
    care = result["mode"] == "care"
    title = {"care": "Care plan", "trip": "Trip plan"}.get(result["mode"], "Weekend plan")
    if result["mode"] == "when":
        title = "Time to meet"
    lines: list[str] = []
    for w in result.get("warnings", []):
        lines.append(f"Note: {w}")
    if result.get("defaults_applied"):
        lines.append(result.get("defaults_note") or
                     "At least one person did not answer, so a middle-of-the-road default was used for them.")
    if care:
        lines.append(result["headline"])
        lines.append("Who owns what (each person sees their own hours privately):")
        for a in result["assignments"]:
            tasks = "; ".join(t["label"] + (" (shared)" if t["shared"] else "") for t in a["tasks"])
            lines.append(f"  {a['name']}: {tasks}")
        if not result["assignments"]:
            lines.append("  Nobody could take on any task with the limits given.")
        for t in result["unfilled_tasks"]:
            lines.append(f"  Still open: {t['label']} ({t['unfilled_hours_bucket']} unfilled)")
        lines.append("Ways to close the gap:")
        lines += [f"  - {o}" for o in result["options"]]
        if result.get("fairness"):
            f = result["fairness"]
            held = ", ".join(f"{n} {c} of {f['plans']}" for n, c in f["held_heavy"].items())
            lines.append(f"Plans in which each person held a heavy task: {held}.")
        lines.append(result["assignment_caveat"])
        lines.append(result["disclaimer"])
    elif result["mode"] == "when":
        lines.append(f"{result['title']}: {result['plan']['span']}.")
        lines.append(result["tradeoff"])
    else:
        if result["plan"]:
            lines.append(f"Plan: {result['plan']['name']}, around {result['plan']['price_band']} per person.")
        else:
            lines.append("No plan fit every limit.")
        lines.append(result["tradeoff"])
    if checkin and checkin.get("complete"):
        lines.append(f"Day-after check-in: {checkin['message']}")
    lines.append(result["honest_limits"])
    text = "\n".join([title, "", *lines])
    markdown = "\n".join([f"# {title}", "", *[ln if ln.startswith("  ") else f"{ln}\n" for ln in lines]])
    return {"title": title, "text": text, "markdown": markdown}
