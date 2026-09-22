import { cn } from "../lib/utils";
import { Input } from "./ui/input";

type Props = {
  label: string;
  name?: string;
  type?: string;
  value?: string | number;
  onChange?: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => void;
  error?: string;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  as?: "input" | "select" | "textarea";
  children?: React.ReactNode;
  className?: string;
  id?: string;
};

export function FormField({
  label,
  name,
  type = "text",
  value,
  onChange,
  error,
  required,
  disabled,
  placeholder,
  as = "input",
  children,
  className,
  id,
}: Props) {
  const fid = id || name || label.replace(/\s+/g, "-").toLowerCase();
  const fieldClass = cn(
    "w-full rounded-md border border-border-strong bg-cream px-3 py-2.5 text-sm text-ink min-h-11",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-peri-300 focus-visible:bg-white",
    error && "border-error",
    disabled && "opacity-50 cursor-not-allowed"
  );
  return (
    <div className={cn("mb-4 max-w-md", className)}>
      <label htmlFor={fid} className="mb-1.5 block text-[13px] font-semibold text-ink">
        {label}
        {required && <span className="text-error"> *</span>}
      </label>
      {as === "select" ? (
        <select id={fid} name={name} className={fieldClass} value={value as string} onChange={onChange} disabled={disabled}>
          {children}
        </select>
      ) : as === "textarea" ? (
        <textarea
          id={fid}
          name={name}
          className={cn(fieldClass, "min-h-24")}
          value={value as string}
          onChange={onChange}
          disabled={disabled}
          placeholder={placeholder}
        />
      ) : (
        <Input
          id={fid}
          name={name}
          type={type}
          value={value as string}
          onChange={onChange as any}
          disabled={disabled}
          placeholder={placeholder}
          className={error ? "border-error" : undefined}
        />
      )}
      {error && (
        <p className="mt-1 text-xs text-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
