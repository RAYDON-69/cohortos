import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; fallback?: ReactNode };
type State = { hasError: boolean; message: string };

/**
 * Prevents blank white screens: any render error shows a recoverable panel.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message || "Something went wrong" };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          role="alert"
          style={{
            padding: 24,
            maxWidth: 480,
            margin: "48px auto",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <h1 style={{ fontSize: 18, marginBottom: 8 }}>This screen hit an error</h1>
          <p style={{ color: "#555", marginBottom: 16 }}>{this.state.message}</p>
          <button type="button" onClick={() => this.setState({ hasError: false, message: "" })}>
            Try again
          </button>
          <button
            type="button"
            style={{ marginLeft: 8 }}
            onClick={() => {
              window.location.href = "/";
            }}
          >
            Go home
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
