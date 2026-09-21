import { StrictMode, Component, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";

class DepsGate extends Component<{ children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null };
  static getDerivedStateFromError(e: Error) {
    const msg = e?.message || String(e);
    if (/Cannot find module|Failed to resolve|framer-motion|tailwind|@radix/i.test(msg)) {
      return {
        err:
          "Frontend dependencies are not installed yet.\n\n" +
          "In a terminal run:\n\n" +
          "  cd frontend\n" +
          "  npm config set registry https://registry.npmjs.org/\n" +
          "  npm install\n" +
          "  npm run dev -- --host 127.0.0.1 --port 5173\n\n" +
          "Then refresh this page.",
      };
    }
    return { err: msg };
  }
  render() {
    if (this.state.err) {
      return (
        <pre style={{ padding: 24, fontFamily: "system-ui", whiteSpace: "pre-wrap", maxWidth: 560 }}>
          {this.state.err}
        </pre>
      );
    }
    return this.props.children;
  }
}

async function boot() {
  try {
    const [{ LocaleProvider }, { default: App }] = await Promise.all([
      import("./i18n/LocaleContext"),
      import("./App"),
    ]);
    await import("./tailwind.css");
    await import("./tokens.css");
    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <DepsGate>
          <HashRouter>
            <LocaleProvider>
              <App />
            </LocaleProvider>
          </HashRouter>
        </DepsGate>
      </StrictMode>
    );
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    document.getElementById("root")!.innerHTML =
      "<pre style=\"padding:24px;font-family:system-ui;white-space:pre-wrap\">" +
      "Could not start the desk UI.\n\n" +
      msg +
      "\n\nIf this mentions missing modules, run:\n  cd frontend && npm install\nthen refresh." +
      "</pre>";
  }
}
boot();
