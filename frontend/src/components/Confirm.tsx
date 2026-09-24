import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";

type Props = {
  open: boolean;
  title: string;
  body?: string;
  consequence?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
  destructive?: boolean;
  loading?: boolean;
};

export function Confirm({
  open,
  title,
  body,
  consequence,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  danger,
  destructive,
  loading,
}: Props) {
  const isDanger = danger || destructive;
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent>
        <h2 className="font-display text-xl font-semibold text-ink">{title}</h2>
        {(body || consequence) && (
          <p className="mt-2 text-sm text-slate-700">{body || consequence}</p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={isDanger ? "destructive" : "default"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ModalConfirm(props: Props) {
  return <Confirm {...props} />;
}

/** Inline confirm used by fee screens */
export function InlineConfirm({
  open = true,
  title,
  message,
  body,
  consequence,
  confirmLabel = "Confirm",
  onConfirm,
  onCancel,
  loading,
  destructive,
}: {
  open?: boolean;
  title?: string;
  message?: string;
  body?: string;
  consequence?: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  destructive?: boolean;
}) {
  if (!open) return null;
  const text = message || body || consequence || title || "Confirm?";
  return (
    <div className="mt-2 rounded-md border border-border bg-cream p-3 text-sm" role="alertdialog">
      <div className="font-semibold text-ink">{text}</div>
      <div className="mt-2 flex gap-2">
        <Button size="sm" variant="outline" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
        <Button size="sm" variant={destructive ? "destructive" : "default"} onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </div>
    </div>
  );
}: Props) {
  if (!open) return null;
  return (
    <div className="mt-2 rounded-md border border-border bg-cream p-3 text-sm" role="alertdialog">
      <div className="font-semibold text-ink">{title}</div>
      {(body || consequence) && <p className="mt-1 text-slate-700">{body || consequence}</p>}
      <div className="mt-2 flex gap-2">
        <Button size="sm" variant="outline" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
        <Button size="sm" variant={destructive ? "destructive" : "default"} onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </div>
    </div>
  );
}
