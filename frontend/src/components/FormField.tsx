import { cn } from "../lib/utils";
import { Input } from "./ui/input";

type FieldWrapProps = {
  id?: string;
  label?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children?: React.ReactNode;
};

export function FormField({ id, label, hint, error, required, className, children }: FieldWrapProps) {
  return (
    <div className={cn("mb-4 max-w-md", className)}>
      {label && (
        <label htmlFor={id} className="mb-1.5 block text-[13px] font-semibold text-ink">
          {label}
          {required && <span className="text-error"> *</span>}
        </label>
      )}
      {children}
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && (
        <p className="mt-1 text-xs text-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

type TextProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string;
};

export function TextInput({
  id,
  name,
  label,
  error,
  className,
  ...rest
}: TextProps) {
  const fid = id || name;
  const input = (
    <Input
      id={fid}
      name={name}
      className={cn(error && "border-error", className)}
      {...rest}
    />
  );
  if (label) {
    return (
      <FormField id={fid} label={label} error={error} required={required}>
        {input}
      </FormField>
    );
  }
  return input;
}

type SelectProps = {
  id?: string;
  name?: string;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  label?: string;
  error?: string;
  children?: React.ReactNode;
};

export function SelectInput({
  id,
  name,
  value,
  onChange,
  disabled,
  required,
  className,
  label,
  error,
  children,
}: SelectProps) {
  const fid = id || name;
  const sel = (
    <select
      id={fid}
      name={name}
      value={value}
      onChange={onChange}
      disabled={disabled}
      required={required}
      className={cn(
        "w-full rounded-md border border-border-strong bg-cream px-3 py-2.5 text-sm text-ink min-h-11",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-peri-300 focus-visible:bg-white",
        error && "border-error",
        disabled && "opacity-50 cursor-not-allowed",
        className
      )}
    >
      {children}
    </select>
  );
  if (label) {
    return (
      <FormField id={fid} label={label} error={error} required={required}>
        {sel}
      </FormField>
    );
  }
  return sel;
}

export function WarningBanner({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "mb-3 rounded-md border border-gold-500/40 bg-gold-bg px-3 py-2 text-sm text-gold-700",
        className
      )}
      role="status"
    >
      {children}
    </div>
  );
}
