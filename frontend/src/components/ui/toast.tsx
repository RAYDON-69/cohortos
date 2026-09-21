import { AnimatePresence, motion } from "framer-motion";

export function Toast({
  open,
  message,
  variant = "info",
  onClose,
}: {
  open: boolean;
  message: string;
  variant?: "info" | "error" | "success";
  onClose?: () => void;
}) {
  const colors =
    variant === "error"
      ? "bg-error-bg text-error border-error/30"
      : variant === "success"
        ? "bg-sage-100 text-sage-900 border-sage-300"
        : "bg-peri-bg text-peri-text border-peri-300/40";
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          className={`fixed bottom-4 right-4 z-[1100] max-w-sm rounded-md border px-4 py-3 text-sm shadow-soft ${colors}`}
          role="status"
        >
          <div className="flex gap-2">
            <span className="flex-1">{message}</span>
            {onClose && (
              <button type="button" className="font-semibold underline" onClick={onClose}>
                Dismiss
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
