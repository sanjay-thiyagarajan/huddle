import type { ShareLine } from "./api";

/** One person's own hours per task. Private: only that person's token returns it. */
export default function MyShare({ name, share, shared }: { name: string; share: ShareLine[]; shared: boolean }) {
  return (
    <section className="myshare" aria-labelledby={`myshare-${name}`}>
      <h3 id={`myshare-${name}`}>Your part, {name}</h3>
      {share.length === 0 ? <p>You aren't assigned a task in this plan.</p> : (
        <ul>{share.map((s) => <li key={s.task_id}>{s.label}: {s.hours} h/week</li>)}</ul>
      )}
      <p className="fine">
        {shared ? "This is shown on a shared screen for the selected profile, so anyone nearby can see it. Use your phone link for more privacy."
                : "Only you see this. The group sees who owns each task, never anyone's hours."}
      </p>
    </section>
  );
}
