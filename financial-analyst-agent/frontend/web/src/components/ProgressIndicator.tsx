"use client";

import { CheckIcon } from "lucide-react";
import type { ProgressStep } from "@/types";

interface ProgressIndicatorProps {
  steps: ProgressStep[];
  visible: boolean;
}

export default function ProgressIndicator({ steps, visible }: ProgressIndicatorProps) {
  if (!visible || steps.length === 0) return null;

  return (
    <div
      className="mx-11 mb-2 px-3.5 py-3 rounded-xl text-xs animate-fade-in"
      style={{
        background: "rgba(15,25,45,0.8)",
        border: "1px solid rgba(59,130,246,0.15)",
        backdropFilter: "blur(8px)",
      }}
    >
      <div className="space-y-1.5">
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1;
          const isDone = step.done;

          return (
            <div key={`${step.node}-${i}`} className="flex items-center gap-2">
              {/* Step indicator */}
              <div className="flex-shrink-0 w-4 h-4 flex items-center justify-center">
                {isDone ? (
                  <div
                    className="w-4 h-4 rounded-full flex items-center justify-center"
                    style={{ background: "rgba(34,197,94,0.2)", border: "1px solid rgba(34,197,94,0.4)" }}
                  >
                    <CheckIcon className="w-2.5 h-2.5" style={{ color: "#86efac" }} />
                  </div>
                ) : isLast ? (
                  <div
                    className="w-4 h-4 rounded-full step-pulse"
                    style={{ background: "rgba(59,130,246,0.3)", border: "1px solid rgba(59,130,246,0.6)" }}
                  />
                ) : (
                  <div
                    className="w-4 h-4 rounded-full"
                    style={{ background: "rgba(34,197,94,0.2)", border: "1px solid rgba(34,197,94,0.4)" }}
                  >
                    <CheckIcon className="w-2.5 h-2.5 m-0.5" style={{ color: "#86efac" }} />
                  </div>
                )}
              </div>

              {/* Label */}
              <span
                style={{
                  color: isDone ? "var(--text-muted)" : isLast ? "#93c5fd" : "var(--text-muted)",
                  fontWeight: isLast && !isDone ? 500 : 400,
                }}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
