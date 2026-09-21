import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { LocaleProvider } from "./i18n/LocaleContext";
import App from "./App";
import "./tailwind.css";
import "./tokens.css";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <LocaleProvider>
        <App />
      </LocaleProvider>
    </HashRouter>
  </StrictMode>
);
