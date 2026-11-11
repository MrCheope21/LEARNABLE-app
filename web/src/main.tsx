import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./styles.css";
import "./dashboard.css";
import "./polish.css";
import "./features.css";
import { registerServiceWorker } from "./pwa";
import { applyTheme, getTheme } from "./theme";

applyTheme(getTheme());
registerServiceWorker();

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
