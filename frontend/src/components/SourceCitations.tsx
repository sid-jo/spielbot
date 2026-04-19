import { useState } from "react";
import { ChevronDown, ChevronUp, BookOpen, MessageSquare, Layers } from "lucide-react";
import type { CitationSource } from "@/lib/games";

interface SourceCitationsProps {
  sources: CitationSource[];
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
          <ChevronUp className="h-3 w-3.5" />
        ) : (
          <ChevronDown className="h-3 w-3.5" />
        )}
      </button>

      {open && (
        <div className="mt-2 space-y-2 animate-float-up">
          {sources.map((s) => (
            <div
              key={`${s.citationIndex}-${s.chunkId ?? s.reference.slice(0, 24)}`}
              className="rounded-lg border-l-[3px] border-green-sage bg-cream p-3 text-xs"
            >
              <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-green-dark">
                <span className="font-mono text-text-muted">[{s.citationIndex}]</span>
                {s.sourceType === "rulebook" ? (
                  <>
                    <BookOpen className="h-3 w-3" />
                    Official Rulebook
                  </>
                ) : s.sourceType === "card" ? (
                  <>
                    <Layers className="h-3 w-3" />
                    Card
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
