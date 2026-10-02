import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import HomeApp from "./home/HomeApp";
import HomePage from "./home/HomePage";
import LinkPage from "./link/LinkPage";
import Simulator from "./simulator/Simulator";
import "./styles.css";

type Tab = "decisions" | "chores";

function Shell() {
  const [tab, setTab] = useState<Tab>(new URLSearchParams(window.location.search).get("tab") === "chores" ? "chores" : "decisions");
  return (
    <>
      <nav className="tabs" aria-label="Huddle">
        <span className="brand">Huddle</span>
        <button className="tab" aria-pressed={tab === "decisions"} onClick={() => setTab("decisions")}>Family decisions</button>
        <button className="tab" aria-pressed={tab === "chores"} onClick={() => setTab("chores")}>Household chores</button>
      </nav>
      {tab === "decisions" ? <Simulator /> : <HomeApp />}
    </>
  );
}

const link = window.location.pathname.match(/^\/r\/(.+)$/);
const homeLink = window.location.pathname.match(/^\/h\/(.+)$/);
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {link ? <LinkPage token={decodeURIComponent(link[1])} /> : homeLink ? <HomePage token={decodeURIComponent(homeLink[1])} /> : <Shell />}
  </StrictMode>,
);
