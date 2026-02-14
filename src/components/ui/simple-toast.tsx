
"use client";

import * as React from "react";
import { X, Check, Info, AlertTriangle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "success" | "error" | "warning";

export interface SimpleToastProps {
    id: number;
    title?: string;
    description: string;
    variant?: ToastVariant;
    duration?: number;
}

interface ToastContextType {
    toast: (props: Omit<SimpleToastProps, "id">) => void;
}

const ToastContext = React.createContext<ToastContextType | undefined>(undefined);

/* ─── Variant Config ─────────────────────────────────────────────── */
const variantConfig = {
    default: {
        Icon: Info,
        ring: "ring-border/40 dark:ring-border/30",
        iconBg: "bg-muted/80 dark:bg-muted/60",
        iconColor: "text-muted-foreground",
        accentBar: "bg-foreground/15 dark:bg-foreground/10",
    },
    success: {
        Icon: Check,
        ring: "ring-emerald-500/15 dark:ring-emerald-500/10",
        iconBg: "bg-emerald-500/10 dark:bg-emerald-500/10",
        iconColor: "text-emerald-600 dark:text-emerald-400",
        accentBar: "bg-emerald-500",
    },
    error: {
        Icon: XCircle,
        ring: "ring-red-500/15 dark:ring-red-500/10",
        iconBg: "bg-red-500/10 dark:bg-red-500/10",
        iconColor: "text-red-600 dark:text-red-400",
        accentBar: "bg-red-500",
    },
    warning: {
        Icon: AlertTriangle,
        ring: "ring-amber-500/15 dark:ring-amber-500/10",
        iconBg: "bg-amber-500/10 dark:bg-amber-500/10",
        iconColor: "text-amber-600 dark:text-amber-400",
        accentBar: "bg-amber-500",
    },
} as const;

/* ─── Toast Item ─────────────────────────────────────────────────── */
function SimpleToastItem({
    id,
    title,
    description,
    variant = "default",
    duration = 3500,
    onClose,
}: SimpleToastProps & { onClose: (id: number) => void }) {
    const [phase, setPhase] = React.useState<"enter" | "idle" | "exit">("enter");
    const [progress, setProgress] = React.useState(100);
    const startTime = React.useRef(Date.now());

    // Animate entrance
    React.useEffect(() => {
        const raf = requestAnimationFrame(() => setPhase("idle"));
        return () => cancelAnimationFrame(raf);
    }, []);

    const handleClose = React.useCallback(() => {
        setPhase("exit");
        setTimeout(() => onClose(id), 280);
    }, [id, onClose]);

    // Auto-dismiss timer + progress bar
    React.useEffect(() => {
        startTime.current = Date.now();
        const interval = setInterval(() => {
            const elapsed = Date.now() - startTime.current;
            const remaining = Math.max(0, 100 - (elapsed / duration) * 100);
            setProgress(remaining);
            if (remaining <= 0) {
                clearInterval(interval);
                handleClose();
            }
        }, 30);
        return () => clearInterval(interval);
    }, [duration, handleClose]);

    const config = variantConfig[variant];
    const { Icon } = config;

    return (
        <div
            className={cn(
                "grid transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] w-full",
                phase === "exit"
                    ? "grid-rows-[0fr] opacity-0 translate-x-3 mb-0"
                    : phase === "enter"
                        ? "grid-rows-[0fr] opacity-0 translate-x-6 mb-0"
                        : "grid-rows-[1fr] opacity-100 translate-x-0 mb-1.5"
            )}
        >
            <div className="overflow-hidden min-h-0">
                <div
                    className={cn(
                        "pointer-events-auto relative flex w-full gap-3",
                        title ? "items-start" : "items-center",
                        "rounded-lg border border-border/60 dark:border-border/40",
                        "bg-card/95 dark:bg-card/90 backdrop-blur-xl backdrop-saturate-150",
                        "shadow-[0_8px_30px_-5px_rgba(0,0,0,0.12),0_2px_8px_-3px_rgba(0,0,0,0.08)]",
                        "dark:shadow-[0_8px_30px_-5px_rgba(0,0,0,0.45),0_2px_8px_-3px_rgba(0,0,0,0.3)]",
                        "ring-1",
                        config.ring,
                        "p-3.5 overflow-hidden",
                    )}
                    role="alert"
                >
                    {/* Accent bar (left edge) */}
                    <div
                        className={cn(
                            "absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg",
                            config.accentBar,
                        )}
                    />

                    {/* Icon container */}
                    <div
                        className={cn(
                            "flex h-7 w-7 items-center justify-center rounded-md shrink-0",
                            config.iconBg,
                        )}
                    >
                        <Icon className={cn("h-3.5 w-3.5", config.iconColor)} />
                    </div>

                    {/* Content */}
                    <div className={cn("flex-1 min-w-0", title && "pt-0.5")}>
                        {title && (
                            <h5 className="font-medium text-[13px] leading-tight text-foreground mb-0.5 truncate">
                                {title}
                            </h5>
                        )}
                        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                            {description}
                        </p>
                    </div>

                    {/* Close button */}
                    <button
                        onClick={handleClose}
                        className={cn(
                            "flex h-5 w-5 items-center justify-center rounded-md shrink-0",
                            "text-muted-foreground/40 hover:text-foreground/80",
                            "hover:bg-muted/80 active:bg-muted",
                            "transition-all duration-150",
                            title && "mt-0.5",
                        )}
                    >
                        <X className="h-3 w-3" />
                    </button>

                    {/* Progress bar (bottom edge) */}
                    <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-border/20 dark:bg-border/10">
                        <div
                            className={cn(
                                "h-full transition-none rounded-full",
                                variant === "default"
                                    ? "bg-foreground/10 dark:bg-foreground/8"
                                    : config.accentBar,
                                variant !== "default" && "opacity-40",
                            )}
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}

/* ─── Provider ───────────────────────────────────────────────────── */
export function SimpleToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = React.useState<SimpleToastProps[]>([]);

    const toast = React.useCallback(
        ({ title, description, variant = "default", duration }: Omit<SimpleToastProps, "id">) => {
            const id = Date.now() + Math.random();
            setToasts((prev) => [...prev, { id, title, description, variant, duration }]);
        },
        [],
    );

    const removeToast = React.useCallback((id: number) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    return (
        <ToastContext.Provider value={{ toast }}>
            {children}
            {/* Toast viewport — bottom-right, above other overlays */}
            <div
                className={cn(
                    "fixed bottom-3 right-3 z-[100]",
                    "flex flex-col-reverse items-end",
                    "w-full max-w-[360px] pointer-events-none",
                )}
            >
                {toasts.map((t) => (
                    <SimpleToastItem key={t.id} {...t} onClose={removeToast} />
                ))}
            </div>
        </ToastContext.Provider>
    );
}

/* ─── Hook ───────────────────────────────────────────────────────── */
export function useSimpleToast() {
    const context = React.useContext(ToastContext);
    if (!context) {
        throw new Error("useSimpleToast must be used within a SimpleToastProvider");
    }
    return context;
}
