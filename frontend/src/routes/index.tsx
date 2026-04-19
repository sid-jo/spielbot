import { createFileRoute } from "@tanstack/react-router";
import { Github } from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import { GameCard } from "@/components/GameCard";
import { SpielbotOracle } from "@/components/SpielbotOracle";
import { games } from "@/lib/games";

const SPIELBOT_REPO_URL = "https://github.com/sid-jo/spielbot";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "SpielBot — Board Game Rules Assistant" },
      {
        name: "description",
        content:
          "Pick your board game and get instant, source-grounded rules answers. Catan, Splendor, and Root supported.",
      },
      { property: "og:title", content: "SpielBot — Board Game Rules Assistant" },
      {
        property: "og:description",
        content:
          "Your board game rules assistant — grounded in official rulebooks and BGG community wisdom.",
      },
    ],
  }),
  component: Index,
});

function Index() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <SiteHeader />

      <main className="flex flex-1 items-center justify-center px-5 py-12">
        <div className="w-full max-w-5xl">
          {/* Brand block */}
          <div className="mb-12 text-center">
            <div className="mb-3 inline-flex items-center gap-3">
              <SpielbotOracle size={64} idleLook trackCursor className="sm:!w-[72px] sm:!h-[72px]" />
              <h1 className="font-display text-5xl font-bold tracking-tight text-green-dark sm:text-6xl">
                SpielBot
              </h1>
            </div>
            <p className="text-base text-text-muted sm:text-lg">
              Choose a game to begin!
            </p>
            <p className="mx-auto mt-2 max-w-md text-sm text-text-muted/80">
              Ask any rules question by text or upload a
              photo of your board.
            </p>
          </div>

          {/* Game cards */}
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {games.map((g) => (
              <GameCard key={g.id} game={g} />
            ))}
          </div>

          <p className="mt-10 text-center font-mono text-[11px] uppercase tracking-[0.2em] text-text-muted/70">
            Grounded in official rulebooks · Backed by community wisdom
          </p>
        </div>
      </main>

      <footer className="mt-auto bg-green-dark px-4 py-3 text-cream">
        <div className="mx-auto flex max-w-3xl flex-col items-center gap-1.5 text-center text-xs leading-snug">
          <p>
            <span className="font-display font-semibold">SpielBot</span>
            {" — "}
            rules assistant by <span className="font-medium">Siddhant Joshi</span>
            {" · "}
            © {new Date().getFullYear()}
          </p>
          <a
            href={SPIELBOT_REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium text-cream underline decoration-cream/45 underline-offset-2 transition-smooth hover:decoration-cream"
          >
            <Github className="h-3.5 w-3.5 shrink-0 opacity-90" aria-hidden />
            GitHub
          </a>
          <p className="max-w-lg text-[10px] leading-snug text-cream/75">
            Catan, Splendor, Root, and related marks are trademarks of their
            respective owners. Not affiliated with any publisher.
          </p>
        </div>
      </footer>
    </div>
  );
}
