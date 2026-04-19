import { useState } from "react";
import { ChevronDown, ChevronUp, BookOpen, MessageSquare } from "lucide-react";
import type { MockSource } from "@/lib/games";

interface SourceCitationsProps {
  sources: MockSource[];
}

export function SourceCitations({ sources }: SourceCitationsProps) {
  const [open, setOpen] = useState(false);

  if (!sources.length) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-text-muted transition-smooth hover:bg-tan/40 hover:text-text-dark"
      >
        <span>📑 Sources</span>
        <span className="font-mono text-[10px]">({sources.length})</span>
        {open ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
      </button>

      {open && (
        <div className="mt-2 space-y-2 animate-float-up">
          {sources.map((s, i) => (
            <div
              key={i}
              className="rounded-lg border-l-[3px] border-green-sage bg-cream p-3 text-xs"
            >
              <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-green-dark">
                {s.type === "rulebook" ? (
                  <>
                    <BookOpen className="h-3 w-3" />
                    Official Rulebook
                  </>
                ) : (
                  <>
                    <MessageSquare className="h-3 w-3" />
                    BGG Community
                  </>
                )}
              </div>
              <p className="leading-relaxed text-text-muted">{s.content}</p>
              <div className="mt-1.5 font-mono text-[10px] text-text-muted/80">
                {s.reference}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
