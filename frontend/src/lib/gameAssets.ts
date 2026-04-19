import type { GameId } from "@/lib/games";
import catanArt from "@/assets/asset-catan.png";
import splendorArt from "@/assets/asset-splendor.png";
import rootArt from "@/assets/asset-root.png";
import catanBanner from "@/assets/banner-catan.jpg";
import splendorBanner from "@/assets/banner-splendor.jpg";
import rootBanner from "@/assets/banner-root.jpg";

/** `background-size` for tiled `gameMotif` (Catan needs width/height to preserve honeycomb aspect). */
export const gameMotifBackgroundSize: Record<GameId, string> = {
  catan: "140px 113px",
  splendor: "88px",
  root: "140px",
};

/** Landing cards use slightly smaller tiles than the chat pane. */
export const gameMotifCardBackgroundSize: Record<GameId, string> = {
  catan: "120px 97px",
  splendor: "88px",
  root: "120px",
};

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
  // True honeycomb repeat: four pointy-top hexes in one translational unit.
  catan: `url("data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='60.62' height='49' viewBox='0 0 60.62 49'><defs><pattern id='hc' width='60.62' height='49' patternUnits='userSpaceOnUse'><path d='M12.12,0 L24.25,7 L24.25,21 L12.12,28 L0,21 L0,7 Z' fill='#E07A2F' fill-opacity='0.38'/><path d='M36.37,0 L48.5,7 L48.5,21 L36.37,28 L24.25,21 L24.25,7 Z' fill='#E07A2F' fill-opacity='0.38'/><path d='M24.25,21 L36.37,28 L36.37,42 L24.25,49 L12.12,42 L12.12,28 Z' fill='#E07A2F' fill-opacity='0.38'/><path d='M48.5,21 L60.62,28 L60.62,42 L48.5,49 L36.37,42 L36.37,28 Z' fill='#E07A2F' fill-opacity='0.38'/></pattern></defs><rect width='200%' height='200%' fill='url(#hc)'/></svg>`,
  )}")`,
  // Gems + coin discs — Splendor (filled like Root trees for consistent subtlety).
  splendor: `url("data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='88' height='88' viewBox='0 0 88 88'><g fill='%231B998B' fill-opacity='0.44'><polygon points='44,6 72,44 44,82 16,44'/><polygon points='68,12 82,28 68,44 54,28'/><polygon points='20,54 34,70 20,86 6,70'/><circle cx='72' cy='64' r='10'/><circle cx='18' cy='26' r='8'/><circle cx='52' cy='76' r='7'/></g></svg>`,
  )}")`,
  // Pine tree silhouettes — Root
  root: `url("data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100' viewBox='0 0 100 100'><g fill='%235B4A3F' opacity='0.45'><path d='M20 78 L12 78 L20 64 L14 64 L22 50 L18 50 L24 38 L30 50 L26 50 L34 64 L28 64 L36 78 L28 78 L28 86 L20 86 Z'/><path d='M70 88 L60 88 L70 70 L62 70 L72 54 L66 54 L74 40 L82 54 L76 54 L86 70 L78 70 L88 88 L78 88 L78 96 L70 96 Z'/></g></svg>`,
  )}")`,
};
