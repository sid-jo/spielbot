import type { GameId } from "@/lib/games";
import catanArt from "@/assets/asset-catan.png";
import splendorArt from "@/assets/asset-splendor.png";
import rootArt from "@/assets/asset-root.png";
import catanBanner from "@/assets/banner-catan.jpg";
import splendorBanner from "@/assets/banner-splendor.jpg";
import rootBanner from "@/assets/banner-root.jpg";

export const gameArt: Record<GameId, string> = {
  catan: catanArt,
  splendor: splendorArt,
  root: rootArt,
};

/**
 * Official-style banner artwork for each game. Used as hero/header imagery
 * in the chat experience and as the primary visual on landing cards.
 */
export const gameBanner: Record<GameId, string> = {
  catan: catanBanner,
  splendor: splendorBanner,
  root: rootBanner,
};

/**
 * Subtle, theme-appropriate background motifs rendered as inline SVG data URIs.
 * These are layered behind the chat surface at very low opacity for game-specific flair.
 */
export const gameMotif: Record<GameId, string> = {
  // Hex grid — Catan
  catan: `url("data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='120' height='104' viewBox='0 0 120 104'><g fill='none' stroke='%23E07A2F' stroke-width='1.2' opacity='0.5'><polygon points='60,4 110,32 110,76 60,100 10,76 10,32'/><polygon points='30,56 50,68 50,88 30,100 10,88 10,68'/><polygon points='90,56 110,68 110,88 90,100 70,88 70,68'/></g></svg>`,
  )}")`,
  // Faceted diamond grid — Splendor
  splendor: `url("data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='80' height='80' viewBox='0 0 80 80'><g fill='none' stroke='%231B998B' stroke-width='1' opacity='0.55'><polygon points='40,8 64,40 40,72 16,40'/><path d='M16 40 L64 40 M28 40 L40 72 M52 40 L40 72 M28 40 L40 8 L52 40'/></g></svg>`,
  )}")`,
  // Pine tree silhouettes — Root
  root: `url("data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100' viewBox='0 0 100 100'><g fill='%235B4A3F' opacity='0.45'><path d='M20 78 L12 78 L20 64 L14 64 L22 50 L18 50 L24 38 L30 50 L26 50 L34 64 L28 64 L36 78 L28 78 L28 86 L20 86 Z'/><path d='M70 88 L60 88 L70 70 L62 70 L72 54 L66 54 L74 40 L82 54 L76 54 L86 70 L78 70 L88 88 L78 88 L78 96 L70 96 Z'/></g></svg>`,
  )}")`,
};
