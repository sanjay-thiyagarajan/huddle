import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import LinkPage from "./link/LinkPage";
import Simulator from "./simulator/Simulator";
import "./styles.css";

const link = window.location.pathname.match(/^\/r\/(.+)$/);
createRoot(document.getElementById("root")!).render(
  <StrictMode>{link ? <LinkPage token={decodeURIComponent(link[1])} /> : <Simulator />}</StrictMode>,
);
