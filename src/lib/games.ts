export type GameId = "catan" | "splendor" | "root";

export interface MockSource {
  type: "rulebook" | "forum";
  content: string;
  reference: string;
}

export interface Game {
  id: GameId;
  name: string;
  emoji: string;
  tagline: string;
  description: string;
  accent: string; // CSS var name, e.g. "catan"
  accentHex: string; // for inline contexts
  starterPrompts: string[];
  mockSources: MockSource[];
}

export const games: Game[] = [
  {
    id: "catan",
    name: "Catan",
    emoji: "🏝️",
    tagline: "Trade, build, settle",
    description:
      "Resource trading, road building, and the longest road — every Catan rule, clarified.",
    accent: "catan",
    accentHex: "#E07A2F",
    starterPrompts: [
      "Can I trade on my first turn?",
      "What happens when the robber is on my hex?",
      "Can I build a road and a settlement in the same turn?",
      "Does the longest road break if it's split?",
    ],
    mockSources: [
      {
        type: "rulebook",
        content:
          "Players may trade resource cards with each other during their own turn, before or after rolling for resources. Trades may not occur on another player's turn.",
        reference: "Catan Rulebook, p. 8",
      },
      {
        type: "forum",
        content:
          "Confirmed by the community — there's no special restriction on trading during your first turn. Standard trading rules apply from turn one onward.",
        reference: "BGG Thread: Trading on Turn 1",
      },
    ],
  },
  {
    id: "splendor",
    name: "Splendor",
    emoji: "💎",
    tagline: "Gems, cards, nobles",
    description:
      "From token economy to noble visits — get crisp answers on every turn action and end-game scoring rule.",
    accent: "splendor",
    accentHex: "#1B998B",
    starterPrompts: [
      "Can I take 2 gems of the same color if only 3 remain?",
      "How does the gold (joker) token work?",
      "When do nobles visit, and can I choose which one?",
      "Can I reserve a face-down card?",
    ],
    mockSources: [
      {
        type: "rulebook",
        content:
          "To take 2 gems of the same color, there must be at least 4 gems of that color available in the supply at the time you take them.",
        reference: "Splendor Rulebook, p. 4",
      },
      {
        type: "forum",
        content:
          "Common house question — the answer is firmly no. The 4-gem requirement is to prevent runaway hoarding of scarce colors.",
        reference: "BGG Thread: Same-color gem rule",
      },
    ],
  },
  {
    id: "root",
    name: "Root",
    emoji: "🌲",
    tagline: "Asymmetric woodland warfare",
    description:
      "Marquise, Eyrie, Alliance, Vagabond — rules guidance for every faction's unique powers.",
    accent: "root",
    accentHex: "#5B4A3F",
    starterPrompts: [
      "How does the Vagabond score points?",
      "Can the Marquise move through a clearing she doesn't rule?",
      "What happens when the Decree has no valid action?",
      "What counts as 'rule' for the Woodland Alliance's outrage?",
    ],
    mockSources: [
      {
        type: "rulebook",
        content:
          "The Vagabond scores victory points by completing quests, aiding other factions, and taking hits on behalf of allies. He may also score by removing buildings and tokens during battle.",
        reference: "Root Law of Root, §C.3",
      },
      {
        type: "forum",
        content:
          "Most players underestimate Aid as a VP source. Aiding a faction with 3+ matching cards in your tableau scores you a point each time.",
        reference: "BGG Thread: Vagabond scoring strategies",
      },
    ],
  },
];

export const getGame = (id: string): Game | undefined =>
  games.find((g) => g.id === id);
