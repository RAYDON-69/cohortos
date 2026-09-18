import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  fallback?: ReactNode;
  /** Called when user clicks Try again — parent should re-fetch */
  onRetry?: () => void;
};
type State = { hasError: boolean; message: string };

/**
 * Prevents blank white screens. Try again dispatches cohortos:retry so screens
 * that listen can reload; Go home navigates to /.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message || "Something went wrong" };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary", error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, message: "" });
    this.props.onRetry?.();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("cohortos:retry"));
    }
  };

  handleHome = () => {
    this.setState({ hasError: false, message: "" });
    if (typeof window !== "undefined") {
      window.location.assign("/");
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          role="alert"
          data-testid="error-boundary"
          style={{
            padding: 24,
            maxWidth: 480,
            margin: "48px auto",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <h1 style={{ fontSize: 18, marginBottom: 8 }}>This screen hit an error</h1>
          <p style={{ color: "#555", marginBottom: 16 }}>{this.state.message}</p>
          <button type="button" onClick={this.handleRetry}>
            Try again
          </button>
          <button type="button" style={{ marginLeft: 8 }} onClick={this.handleHome}>
            Go home
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
