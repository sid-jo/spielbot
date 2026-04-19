export type GameId = "catan" | "splendor" | "root";

/** Retrieved chunk for citations — order matches [1], [2], … in the answer. */
export interface CitationSource {
  citationIndex: number;
  sourceType: "rulebook" | "card" | "forum";
  content: string;
  reference: string;
  chunkId?: string;
}

/** Static copy on the landing page (not used for live API replies). */
export interface MockSource {
  citationIndex: number;
  sourceType: "rulebook" | "forum";
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
    tagline: "Klaus Teuber | 1995",
    description:
      "Collect and trade resources to build up the island of Catan",
    accent: "catan",
    accentHex: "#b63f41",
    starterPrompts: [
      "Can I trade on my first turn?",
      "What happens when the robber is on my hex?",
      "Can I build a road and a settlement in the same turn?",
      "Does the longest road break if it's split?",
    ],
    mockSources: [
      {
        citationIndex: 1,
        sourceType: "rulebook",
        content:
          "Players may trade resource cards with each other during their own turn, before or after rolling for resources. Trades may not occur on another player's turn.",
        reference: "Catan Rulebook, p. 8",
      },
      {
        citationIndex: 2,
        sourceType: "forum",
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
    tagline: "Mark Andre | 2014",
    description:
      "Dominate the Silk Road to become the most prestigious merchant in the world",
    accent: "splendor",
    accentHex: "#15294a",
    starterPrompts: [
      "Can I take 2 gems of the same color if only 3 remain?",
      "How does the gold (joker) token work?",
      "When do nobles visit, and can I choose which one?",
      "Can I reserve a face-down card?",
    ],
    mockSources: [
      {
        citationIndex: 1,
        sourceType: "rulebook",
        content:
          "To take 2 gems of the same color, there must be at least 4 gems of that color available in the supply at the time you take them.",
        reference: "Splendor Rulebook, p. 4",
      },
      {
        citationIndex: 2,
        sourceType: "forum",
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
    tagline: "Cole Werhle | 2018",
    description:
      "Decide the fate of the Woodland as asymmetric factions fight for contrasting goals",
    accent: "root",
    accentHex: "#3f5a51",
    starterPrompts: [
      "How does the Vagabond score points?",
      "When can an ambush card be used?",
      "What happens when the Decree has no valid action?",
      "How do you determine 'rule'?",
    ],
    mockSources: [
      {
        citationIndex: 1,
        sourceType: "rulebook",
        content:
          "The Vagabond scores victory points by completing quests, aiding other factions, and taking hits on behalf of allies. He may also score by removing buildings and tokens during battle.",
        reference: "Root Law of Root, §C.3",
      },
      {
        citationIndex: 2,
        sourceType: "forum",
        content:
          "Most players underestimate Aid as a VP source. Aiding a faction with 3+ matching cards in your tableau scores you a point each time.",
        reference: "BGG Thread: Vagabond scoring strategies",
      },
    ],
  },
];

export const getGame = (id: string): Game | undefined =>
  games.find((g) => g.id === id);
