import { useCallback, useEffect, useState } from "react";
import { Activity, AgentBox, ChoreBoard, FairnessCard, MyWeek, ProfilePanel } from "./Panels";
import { homeApi } from "./homeApi";
import type { HomeState } from "./homeApi";

/** One member's view of the household: their private panels on the left, the shared board on the right. */
export default function HomeView({ token, sharedScreen }: { token: string; sharedScreen: boolean }) {
  const [st, setSt] = useState<HomeState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try { setSt(await homeApi.state(token)); setError(null); } catch (e) { setError((e as Error).message); }
  }, [token]);

  useEffect(() => {
    setSt(null);
    void refresh();
    const id = setInterval(() => void refresh(), 4000);
    return () => clearInterval(id);
  }, [refresh]);

  if (error && !st) return <p className="error" role="alert">{error}</p>;
  if (!st) return <p>Loading</p>;
  return (
    <div className="home-layout">
      <div className="home-private">
        {sharedScreen && (
          <p className="fine">Showing {st.me.name}'s private panels. On a shared screen, anyone nearby can see them. A phone link is more private.</p>
        )}
        <ProfilePanel token={token} profile={st.mine.profile} onSaved={() => void refresh()} />
        <MyWeek token={token} st={st} onChange={setSt} />
        <AgentBox token={token} onChanged={() => void refresh()} />
      </div>
      <div className="home-shared">
        <ChoreBoard token={token} st={st} onChange={setSt} />
        <FairnessCard st={st} />
        <Activity st={st} />
      </div>
    </div>
  );
}
