import { createFileRoute } from "@tanstack/react-router";
import { SiteHeader } from "@/components/SiteHeader";
import { GameCard } from "@/components/GameCard";
import { SpielbotOracle } from "@/components/SpielbotOracle";
import { games } from "@/lib/games";

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
    </div>
  );
}
