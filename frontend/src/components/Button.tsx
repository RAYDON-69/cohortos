import React from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "outline" | "ghost" | "disabled";
export type ButtonSize = "default" | "sm";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** Reason shown when disabled — required by §4.1 */
  disabledReason?: string;
  children: React.ReactNode;
}

/**
 * Button — all states per design-system.md §4.1
 * Focus ring is global from tokens.css (:focus-visible).
 */
export function Button({
  variant = "primary",
  size = "default",
  loading = false,
  disabled,
  disabledReason,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || variant === "disabled" || loading;
  const classes = [
    "btn",
    `btn-${variant === "disabled" ? "disabled" : variant}`,
    size === "sm" ? "btn-sm" : "",
    loading ? "btn-loading" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type={type}
      className={classes}
      disabled={isDisabled}
      aria-disabled={isDisabled}
      aria-busy={loading || undefined}
      title={isDisabled && disabledReason ? disabledReason : undefined}
      {...rest}
    >
      {loading ? <span className="btn-loading-label">{children}</span> : children}
    </button>
  );
}
