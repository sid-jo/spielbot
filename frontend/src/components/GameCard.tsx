import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import type { Game } from "@/lib/games";
import {
  gameArt,
  gameMotif,
  gameMotifCardBackgroundSize,
} from "@/lib/gameAssets";

interface GameCardProps {
  game: Game;
}

export function GameCard({ game }: GameCardProps) {
  return (
    <Link
      to="/chat/$gameId"
      params={{ gameId: game.id }}
      className="group relative flex flex-col items-center gap-4 overflow-hidden rounded-xl border-2 border-tan bg-card p-7 text-center shadow-soft transition-smooth hover:-translate-y-1 hover:shadow-lift"
      style={{ ["--accent" as string]: game.accentHex }}
      onMouseEnter={(e) =>
        (e.currentTarget.style.borderColor = game.accentHex)
      }
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "")}
    >
      {/* Game-specific motif watermark */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.08] transition-smooth group-hover:opacity-[0.14]"
        style={{
          backgroundImage: gameMotif[game.id],
          backgroundSize: gameMotifCardBackgroundSize[game.id],
        }}
      />

      {/* Asset artwork */}
      <div
        className="relative flex h-28 w-28 items-center justify-center rounded-full bg-cream transition-smooth group-hover:scale-105"
        style={{
          boxShadow: `inset 0 0 0 1px ${game.accentHex}25, 0 6px 18px -8px ${game.accentHex}55`,
        }}
      >
        <img
          src={gameArt[game.id]}
          alt={`${game.name} game piece illustration`}
          width={224}
          height={224}
          loading="lazy"
          className="h-24 w-24 object-contain drop-shadow-sm"
        />
      </div>

      <div className="relative">
        <h3 className="font-display text-2xl font-bold text-text-dark">
          {game.name}
        </h3>
        <p className="mt-1 text-sm text-text-muted">{game.tagline}</p>
      </div>

      <p className="relative text-xs leading-relaxed text-text-muted">
        {game.description}
      </p>

      <div
        className="relative mt-1 inline-flex items-center gap-1.5 text-sm font-semibold transition-smooth group-hover:gap-2.5"
        style={{ color: game.accentHex }}
      >
        Start playing
        <ArrowRight className="h-4 w-4" />
      </div>
    </Link>
  );
}
