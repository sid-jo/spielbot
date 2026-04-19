import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Trash2,
  Shuffle,
  ChevronDown,
  ChevronUp,
  X,
  BookOpen,
  MessagesSquare,
  ImageIcon,
} from "lucide-react";
import type { Game } from "@/lib/games";
import { gameArt, gameMotif } from "@/lib/gameAssets";
import { SpielbotOracle } from "@/components/SpielbotOracle";

interface ChatSidebarProps {
  game: Game;
  onNewChat: () => void;
  onClose?: () => void;
}

export function ChatSidebar({ game, onNewChat, onClose }: ChatSidebarProps) {
  const [aboutOpen, setAboutOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <aside className="relative flex h-full w-full flex-col overflow-hidden bg-green-dark text-cream">
      {/* Game-themed motif backdrop */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage: gameMotif[game.id],
          backgroundSize: "100px",
        }}
      />

      {/* Header */}
      <div className="relative flex items-center justify-between p-5">
        <Link to="/" className="flex items-center gap-2">
          <SpielbotOracle size={28} idleLook={false} />
          <span className="font-display text-lg font-bold tracking-tight">
            SpielBot
          </span>
        </Link>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-cream/70 transition-smooth hover:bg-white/10 hover:text-cream lg:hidden"
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Current game — featured artwork card */}
      <div
        className="relative mx-5 overflow-hidden rounded-xl bg-white/5 p-4"
        style={{
          boxShadow: `inset 0 0 0 1px ${game.accentHex}40`,
        }}
      >
        <div
          className="absolute -right-6 -top-6 h-32 w-32 rounded-full opacity-30 blur-2xl"
          style={{ background: game.accentHex }}
        />
        <div className="relative flex items-center gap-3">
          <div
            className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-cream"
            style={{ boxShadow: `0 4px 12px -4px ${game.accentHex}80` }}
          >
            <img
              src={gameArt[game.id]}
              alt=""
              width={128}
              height={128}
              loading="lazy"
              className="h-14 w-14 object-contain"
            />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-cream/60">
              Currently playing
            </div>
            <div className="font-display text-base font-semibold leading-tight">
              {game.name}
            </div>
            <div
              className="mt-0.5 text-xs"
              style={{ color: `${game.accentHex}` }}
            >
              {game.tagline}
            </div>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="relative mt-5 flex flex-col gap-2 px-5">
        <button
          onClick={onNewChat}
          className="flex items-center justify-center gap-2 rounded-md bg-green-sage px-4 py-2.5 text-sm font-medium text-cream transition-smooth hover:brightness-110"
        >
          <Trash2 className="h-4 w-4" />
          New Chat
        </button>
        <button
          onClick={() => navigate({ to: "/" })}
          className="flex items-center justify-center gap-2 rounded-md border border-cream/20 bg-transparent px-4 py-2.5 text-sm font-medium text-cream transition-smooth hover:bg-white/10"
        >
          <Shuffle className="h-4 w-4" />
          Switch Game
        </button>
      </div>

      {/* About */}
      <div className="relative mt-auto p-5">
        <button
          onClick={() => setAboutOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-xs font-mono uppercase tracking-[0.18em] text-cream/70 transition-smooth hover:text-cream"
        >
          About SpielBot
          {aboutOpen ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>
        {aboutOpen && (
          <div className="mt-2 space-y-3 rounded-md bg-white/5 p-3 text-xs leading-relaxed text-cream/85">
            <p>
              SpielBot answers board game rules questions using
              retrieval-augmented generation over official rulebooks and
              BoardGameGeek community discussions.
            </p>
            <ul className="space-y-1.5">
              <li className="flex items-start gap-2">
                <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-sage" />
                <span>Grounded in official rules + community wisdom</span>
              </li>
              <li className="flex items-start gap-2">
                <ImageIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-sage" />
                <span>Image upload for game state queries</span>
              </li>
              <li className="flex items-start gap-2">
                <MessagesSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-sage" />
                <span>Source citations for every answer</span>
              </li>
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
}
