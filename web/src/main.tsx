import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./styles.css";
import "./dashboard.css";
import "./polish.css";
import "./features.css";
import { detectLanguage, loadCatalog } from "./i18n";
import { registerServiceWorker } from "./pwa";
import { applyTheme, getTheme } from "./theme";

applyTheme(getTheme());
registerServiceWorker();

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

// The browser's language first, so the first screen is not shown in English and then replaced.
void loadCatalog(detectLanguage())
  .catch(() => undefined)
  .then(() =>
    createRoot(root).render(
      <StrictMode>
        <App />
      </StrictMode>,
    ),
  );
