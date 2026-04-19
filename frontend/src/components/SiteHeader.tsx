import { Link } from "@tanstack/react-router";
import { SpielbotOracle } from "@/components/SpielbotOracle";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-cream/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
        <Link to="/" className="group flex items-center gap-2">
          <SpielbotOracle size={28} idleLook={false} title="SpielBot" />
          <span className="font-display text-lg font-bold tracking-tight text-green-dark">
            SpielBot
          </span>
        </Link>
        <span className="hidden text-xs font-medium uppercase tracking-[0.18em] text-text-muted sm:inline">
          Board game rules assistant
        </span>
      </div>
    </header>
  );
}
