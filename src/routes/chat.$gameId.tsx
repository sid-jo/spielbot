import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { SiteHeader } from "@/components/SiteHeader";
import { ChatWindow } from "@/components/ChatWindow";
import { getGame, games } from "@/lib/games";

export const Route = createFileRoute("/chat/$gameId")({
  loader: ({ params }) => {
    const game = getGame(params.gameId);
    if (!game) throw notFound();
    return { game };
  },
  head: ({ loaderData }) => ({
    meta: loaderData
      ? [
          { title: `${loaderData.game.name} Rules — SpielBot` },
          {
            name: "description",
            content: `Ask SpielBot any ${loaderData.game.name} rules question. Text or board photos welcome.`,
          },
          {
            property: "og:title",
            content: `${loaderData.game.name} Rules Assistant — SpielBot`,
          },
          {
            property: "og:description",
            content: `Get instant, source-grounded answers about ${loaderData.game.name}.`,
          },
        ]
      : [],
  }),
  notFoundComponent: NotFound,
  errorComponent: ({ error }) => (
    <div className="flex min-h-screen items-center justify-center bg-background p-6 text-center">
      <div>
        <p className="text-destructive">Something went wrong: {error.message}</p>
        <Link to="/" className="mt-4 inline-block text-green-dark underline">
          Back to games
        </Link>
      </div>
    </div>
  ),
  component: ChatPage,
});

function ChatPage() {
  const { game } = Route.useLoaderData();
  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <ChatWindow game={game} />
    </div>
  );
}

function NotFound() {
  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <div className="mx-auto max-w-2xl px-6 py-24 text-center">
        <h1 className="font-display text-4xl font-bold text-text-dark">
          Game not found
        </h1>
        <p className="mt-3 text-text-muted">
          We don't have a SpielBot session for that game yet. Choose from one of
          these:
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          {games.map((g) => (
            <Link
              key={g.id}
              to="/chat/$gameId"
              params={{ gameId: g.id }}
              className="rounded-full border border-tan bg-card px-5 py-2.5 text-sm font-medium text-text-dark shadow-soft transition-smooth hover:border-green-sage"
            >
              {g.emoji} {g.name}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
