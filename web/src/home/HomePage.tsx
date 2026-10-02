import HomeView from "./HomeView";

/** /h/<token>: one member's own page, usable from their phone. */
export default function HomePage({ token }: { token: string }) {
  return (
    <main className="home-app">
      <header className="home-head">
        <h1>Your household, privately</h1>
        <p className="fine">This page is just for you. Your limits and preferences are never shown to anyone else, and the group is never told who set what.</p>
      </header>
      <HomeView token={token} sharedScreen={false} />
    </main>
  );
}
