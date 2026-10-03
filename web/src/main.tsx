import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import HomeApp from "./home/HomeApp";
import HomePage from "./home/HomePage";
import LinkPage from "./link/LinkPage";
import { Brand } from "./Logo";
import Simulator from "./simulator/Simulator";
import "./styles.css";

type Tab = "decisions" | "home";

function Shell() {
  const [tab, setTab] = useState<Tab>(["decisions"].includes(new URLSearchParams(window.location.search).get("tab") ?? "") ? "decisions" : "home");
  return (
    <>
      <nav className="tabs" aria-label="Huddle">
        <Brand />
        <button className="tab" aria-pressed={tab === "home"} onClick={() => setTab("home")}>Home</button>
        <button className="tab" aria-pressed={tab === "decisions"} onClick={() => setTab("decisions")}>Try a decision</button>
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
