import { cn } from "../lib/utils";
export {
  Card as UiCard,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "./ui/card";

type Props = React.HTMLAttributes<HTMLDivElement> & {
  variant?: string;
};

export function Card({ className, variant, ...props }: Props) {
  return (
    <div
      className={cn(
        "rounded-card border border-border bg-white p-6 shadow-soft text-left",
        variant === "muted" && "bg-sage-100/50",
        variant === "outline" && "shadow-none",
        className
      )}
      {...props}
    />
  );
}
