import { Component, type ErrorInfo, type ReactNode } from "react";
import { Link } from "react-router-dom";

type Props = { children: ReactNode; fallbackTitle?: string };
type State = { error: Error | null };

/**
 * Never allow a white dead-end screen. Any render crash surfaces recovery UI.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[CohortOS] screen crash", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="login-page" role="alert" data-testid="error-boundary">
          <div className="login-card" style={{ maxWidth: 480 }}>
            <h1 className="view-title">{this.props.fallbackTitle || "Something went wrong"}</h1>
            <p className="caption muted" style={{ marginBottom: 12 }}>
              This screen failed to load. You can go back to the desk — your session is still active.
            </p>
            <pre
              className="mono-data"
              style={{
                fontSize: 12,
                maxHeight: 120,
                overflow: "auto",
                background: "var(--surface-2, #f4f4f5)",
                padding: 8,
                borderRadius: 8,
              }}
            >
              {this.state.error.message}
            </pre>
            <p style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Link to="/attendance" className="btn btn-primary">
                Back to attendance
              </Link>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => this.setState({ error: null })}
              >
                Try again
              </button>
            </p>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
