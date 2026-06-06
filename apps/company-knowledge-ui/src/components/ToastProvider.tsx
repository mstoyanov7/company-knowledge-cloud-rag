import { Check, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type ToastKind = "info" | "ok" | "err";
type Toast = { id: number; message: string; kind: ToastKind };

type ToastContextValue = {
  toast: (message: string, kind?: ToastKind) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) {
    return { toast: () => undefined };
  }
  return value;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, kind: ToastKind = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, kind }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id));
    }, 3200);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-wrap" role="status" aria-live="polite">
        {toasts.map((item) => (
          <div key={item.id} className={item.kind === "ok" ? "toast ok" : item.kind === "err" ? "toast err" : "toast"}>
            {item.kind === "ok" ? (
              <Check size={16} aria-hidden="true" />
            ) : item.kind === "err" ? (
              <X size={16} aria-hidden="true" />
            ) : (
              <Info size={16} aria-hidden="true" />
            )}
            <span>{item.message}</span>
            <button className="toast__x" type="button" onClick={() => dismiss(item.id)} aria-label="Dismiss">
              <X size={13} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
