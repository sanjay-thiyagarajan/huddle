import { TASK_TYPES } from "./api";

export interface TaskDraft { label: string; type: string; hours: number }

export const DEFAULT_TASKS: TaskDraft[] = [
  { label: "Daily check-in", type: "checkin", hours: 7 },
  { label: "Appointments and transport", type: "appointments", hours: 6 },
  { label: "Meals", type: "meals", hours: 8 },
  { label: "Finances and paperwork", type: "finances", hours: 3 },
  { label: "Overnight cover", type: "overnight", hours: 6 },
];

export const needPayload = (tasks: TaskDraft[], dollars: number) => ({
  tasks: tasks.map((t, i) => ({ id: `t${i}_${t.type}`, label: t.label, type: t.type, hours: Number(t.hours) })),
  dollars_per_month: Number(dollars),
});

/** The care need everyone can see: tasks with weekly hours, and the monthly money needed. */
export default function NeedEditor({ tasks, dollars, onTasks, onDollars, summary }: {
  tasks: TaskDraft[]; dollars: number; onTasks: (t: TaskDraft[]) => void; onDollars: (d: number) => void; summary: string;
}) {
  const setTask = (i: number, patch: Partial<TaskDraft>) => onTasks(tasks.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  return (
    <details className="need-editor">
      <summary>{summary} ({tasks.reduce((n, t) => n + Number(t.hours || 0), 0)} h/week, ${dollars}/month)</summary>
      <p className="fine">Everyone can see this part. Only the amounts people can give stay private.</p>
      {tasks.map((t, i) => (
        <div className="task-row" key={i}>
          <input aria-label={`Task ${i + 1} name`} value={t.label} onChange={(e) => setTask(i, { label: e.target.value })} />
          <select aria-label={`Task ${i + 1} type`} value={t.type} onChange={(e) => setTask(i, { type: e.target.value })}>
            {TASK_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input aria-label={`Task ${i + 1} hours per week`} type="number" min={1} max={80} value={t.hours}
            onChange={(e) => setTask(i, { hours: Number(e.target.value) })} />
        </div>
      ))}
      <div className="row">
        {tasks.length < 20 && <button type="button" className="ghost" onClick={() => onTasks([...tasks, { label: "New task", type: "checkin", hours: 1 }])}>Add a task</button>}
        {tasks.length > 1 && <button type="button" className="ghost" onClick={() => onTasks(tasks.slice(0, -1))}>Remove last</button>}
      </div>
      <label>Money needed per month (dollars)
        <input type="number" min={0} value={dollars} onChange={(e) => onDollars(Number(e.target.value))} />
      </label>
      <p className="fine">Decision aid, not medical, legal or financial advice. Don't enter health details.</p>
    </details>
  );
}
