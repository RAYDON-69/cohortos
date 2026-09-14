import React from "react";
import "./FormField.css";

export interface FormFieldProps {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}

/**
 * Form field §4.6 — label always above, never placeholder-as-label.
 * Inline validation in error color, plain language.
 */
export function FormField({
  id,
  label,
  error,
  hint,
  required,
  children,
  className = "",
}: FormFieldProps) {
  return (
    <div className={`form-field ${error ? "has-error" : ""} ${className}`}>
      <label htmlFor={id} className="form-label">
        {label}
        {required && <span className="form-required" aria-hidden="true"> *</span>}
      </label>
      {children}
      {error && (
        <div className="form-error" role="alert" id={`${id}-error`}>
          {error}
        </div>
      )}
      {!error && hint && <div className="form-hint caption">{hint}</div>}
    </div>
  );
}

export interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  hasError?: boolean;
}

export function TextInput({ hasError, className = "", ...rest }: TextInputProps) {
  return (
    <input
      className={`form-input ${hasError ? "form-input-error" : ""} ${className}`}
      aria-invalid={hasError || undefined}
      {...rest}
    />
  );
}

export function SelectInput({
  hasError,
  className = "",
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement> & { hasError?: boolean }) {
  return (
    <select
      className={`form-input form-select ${hasError ? "form-input-error" : ""} ${className}`}
      aria-invalid={hasError || undefined}
      {...rest}
    >
      {children}
    </select>
  );
}

/** Warning banner above form — not a modal (§4.6) */
export function WarningBanner({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`warning-banner ${className}`} role="alert">
      {children}
    </div>
  );
}
