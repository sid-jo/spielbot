"""
End-to-end SpielBot pipeline: session state, retrieval + generation, and CLI.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from bgg_config import GAMES
from generate import GeneratorResponse, generate, generate_stream
from index import ChunkIndex, ChunkResult
from prompts import get_system_prompt
from retrieve import format_context, retrieve_split

MAX_HISTORY_TURNS = 10  # max Q&A pairs to keep (20 messages)

_GAME_LABELS = {
    "catan": "Catan",
    "splendor": "Splendor",
    "root": "Root",
}


@dataclass
class SpielBotAnswer:
    """Complete answer package returned by the orchestrator."""

    answer: str
    game_name: str
    query: str
    sources: list[ChunkResult]
    generator_response: GeneratorResponse
    error: str | None = None


class SpielBotSession:
    """
    Stateful session for one user's interaction with SpielBot.

    Lifecycle:
        session = SpielBotSession()
        session.select_game("root")
        answer = session.ask("Can the Marquise craft cards?")
        answer2 = session.ask("How many workshops does she start with?")
        session.select_game("catan")   # resets history
        answer3 = session.ask("Can I trade on my first turn?")
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        index: ChunkIndex | None = None,
        eager_load: bool = False,
    ):
        self._model = model
        self._temperature = temperature
        self._index = index
        self._game_name: str | None = None
        self._system_prompt: str = ""
        self._history: list[dict] = []
        if eager_load and self._index is None:
            self._load_index()

    def _load_index(self) -> None:
        """Load ChunkIndex immediately. Call during startup."""
        project_root = Path(__file__).parent.parent
        self._index = ChunkIndex(project_root)

    @property
    def game_name(self) -> str | None:
        return self._game_name

    @property
    def has_game(self) -> bool:
        return self._game_name is not None

    @property
    def history(self) -> list[dict]:
        """Return a copy of the conversation history."""
        return list(self._history)

    def _get_index(self) -> ChunkIndex:
        if self._index is None:
            self._load_index()
        return self._index

    def select_game(self, game_name: str) -> None:
        """
        Set the active game. Resets conversation history and
        loads the game-specific system prompt.

        Raises ValueError if game_name is not in GAMES.
        """
        if game_name not in GAMES:
            raise ValueError(
                f"Unknown game '{game_name}'. "
                f"Valid options: {', '.join(GAMES)}"
            )
        self._game_name = game_name
        self._system_prompt = get_system_prompt(game_name)
        self._history = []

    def reset_chat(self) -> None:
        """Clear conversation history without changing the active game."""
        self._history = []

    def get_available_games(self) -> list[str]:
        """Return list of valid game names."""
        return list(GAMES.keys())

    def ask(
        self,
        query: str,
        rules_top_k: int = 3,
        forum_top_k: int = 3,
    ) -> SpielBotAnswer:
        """
        Answer a question in the context of the current game + conversation.

        Steps:
          1. Validate state (game must be selected)
          2. Retrieve: 3 rulebook+card chunks + 3 forum chunks
          3. Format context
          4. Generate with conversation history
          5. Append Q&A to history
          6. Return SpielBotAnswer
        """
        if not self.has_game:
            return SpielBotAnswer(
                answer="",
                game_name="",
                query=query,
                sources=[],
                generator_response=GeneratorResponse(
                    answer="",
                    game_name="",
                    model="",
                    query=query,
                    num_sources=0,
                    error="No game selected",
                ),
                error="No game selected. Call select_game() first.",
            )

        idx = self._get_index()
        results = retrieve_split(
            idx,
            query,
            self._game_name,
            rules_top_k=rules_top_k,
            forum_top_k=forum_top_k,
        )

        if not results:
            no_results = (
                "I couldn't find any relevant sources for your question. "
                "Try rephrasing, or make sure you've selected the right game."
            )
            return SpielBotAnswer(
                answer=no_results,
                game_name=self._game_name,
                query=query,
                sources=[],
                generator_response=GeneratorResponse(
                    answer=no_results,
                    game_name=self._game_name,
                    model="",
                    query=query,
                    num_sources=0,
                ),
            )

        context = format_context(results)
        source_ids = [r.chunk_id for r in results]

        gen_kwargs: dict = {}
        if self._model is not None:
            gen_kwargs["model"] = self._model
        if self._temperature is not None:
            gen_kwargs["temperature"] = self._temperature

        gen_response = generate(
            query=query,
            game_name=self._game_name,
            context=context,
            source_ids=source_ids,
            system_prompt=self._system_prompt,
            history=self._history,
            **gen_kwargs,
        )

        if not gen_response.error:
            self._history.append({"role": "user", "content": query})
            self._history.append(
                {"role": "assistant", "content": gen_response.answer}
            )
            if len(self._history) > MAX_HISTORY_TURNS * 2:
                self._history = self._history[-(MAX_HISTORY_TURNS * 2) :]

        return SpielBotAnswer(
            answer=gen_response.answer,
            game_name=self._game_name,
            query=query,
            sources=results,
            generator_response=gen_response,
            error=gen_response.error,
        )

    def ask_stream(
        self,
        query: str,
        rules_top_k: int = 3,
        forum_top_k: int = 3,
    ) -> tuple[list[ChunkResult], Generator[str, None, GeneratorResponse]]:
        """
        Streaming variant of ask(). Returns retrieved sources and a
        generator that yields tokens.

        Returns:
            (sources, token_generator)
            - sources: list of ChunkResult for citation display
            - token_generator: yields str tokens; final GeneratorResponse
              is accessible via StopIteration.value

        The caller is responsible for consuming the generator and
        appending to history afterward.
        """
        if not self.has_game:
            raise ValueError("No game selected. Call select_game() first.")

        idx = self._get_index()
        results = retrieve_split(
            idx,
            query,
            self._game_name,
            rules_top_k=rules_top_k,
            forum_top_k=forum_top_k,
        )

        if not results:
            no_results = (
                "I couldn't find any relevant sources for your question. "
                "Try rephrasing, or make sure you've selected the right game."
            )

            def _empty_stream() -> Generator[str, None, GeneratorResponse]:
                yield no_results
                return GeneratorResponse(
                    answer=no_results,
                    game_name=self._game_name,
                    model="",
                    query=query,
                    num_sources=0,
                    source_ids=[],
                )

            return [], _empty_stream()

        context = format_context(results)
        source_ids = [r.chunk_id for r in results]

        gen_kwargs: dict = {}
        if self._model is not None:
            gen_kwargs["model"] = self._model
        if self._temperature is not None:
            gen_kwargs["temperature"] = self._temperature

        streamer = generate_stream(
            query=query,
            game_name=self._game_name,
            context=context,
            source_ids=source_ids,
            system_prompt=self._system_prompt,
            history=self._history,
            **gen_kwargs,
        )

        return results, streamer

    def commit_to_history(self, query: str, answer: str) -> None:
        """
        Append a completed Q&A pair to conversation history.
        Call this after consuming the stream from ask_stream().
        """
        self._history.append({"role": "user", "content": query})
        self._history.append({"role": "assistant", "content": answer})
        if len(self._history) > MAX_HISTORY_TURNS * 2:
            self._history = self._history[-(MAX_HISTORY_TURNS * 2) :]


def _print_sources(sources: list[ChunkResult], show_sources: bool) -> None:
    """Print source counts and optional chunk details (matches _print_answer)."""
    if not sources:
        return
    n_official = sum(
        1 for s in sources if s.source_type in ("rulebook", "card")
    )
    n_forum = sum(1 for s in sources if s.source_type == "forum")
    print(f"  Sources: {n_official} rulebook, {n_forum} forum")
    if show_sources:
        from retrieve import _format_result_header

        print()
        for i, r in enumerate(sources, 1):
            print(_format_result_header(i, r))
            prev = r.content
            if len(prev) > 200:
                prev = prev[:200] + "..."
            print(f"    {prev}")
            print()


def _print_answer(result: SpielBotAnswer, show_sources: bool) -> None:
    """Format and print a SpielBotAnswer for terminal display."""
    if result.error:
        print(f"Error: {result.error}")
        return
    print()
    print(f"SpielBot: {result.answer}")
    print()
    _print_sources(result.sources, show_sources)


def _print_game_header(game_name: str) -> None:
    """Print the session banner for the active game."""
    label = _GAME_LABELS.get(game_name, game_name.title())
    line = "━" * 34
    print()
    print(line)
    print(f"  SpielBot — {label}")
    print(line)
    print("  Type your question, or:")
    print("    /game    — switch game")
    print("    /clear   — clear chat history")
    print("    /sources — toggle source display")
    print("    /quit    — exit")
    print()


def _prompt_game_choice(session: SpielBotSession) -> str:
    """Display game selection menu and return chosen game_name."""
    games = session.get_available_games()
    print()
    print("Select a game:")
    for i, g in enumerate(games, 1):
        label = _GAME_LABELS.get(g, g.title())
        print(f"  [{i}] {label}")
    while True:
        try:
            raw = input("\nChoice> ").strip()
        except EOFError:
            return ""
        if not raw.isdigit():
            print("Enter a number.")
            continue
        choice = int(raw)
        if 1 <= choice <= len(games):
            return games[choice - 1]
        print(f"Enter 1–{len(games)}.")


def _interactive_loop(
    session: SpielBotSession,
    show_sources: bool,
    verbose: bool,
) -> None:
    """Main REPL loop."""
    line = "━" * 34
    print()
    print(line)
    print("  🎲 SpielBot")
    print(line)
    print()
    print("  Loading indexes...")
    session._load_index()
    print("  Ready!\n")

    chosen = _prompt_game_choice(session)
    if not chosen:
        return
    session.select_game(chosen)
    _print_game_header(session.game_name or "")

    while True:
        try:
            q = input("Question> ").strip()
        except EOFError:
            break
        if not q:
            continue
        low = q.lower()
        if low in ("/quit", "/exit"):
            break
        if low == "/clear":
            session.reset_chat()
            print("  Chat history cleared.\n")
            continue
        if low == "/sources":
            show_sources = not show_sources
            state = "on" if show_sources else "off"
            print(f"  Source details {state}.\n")
            continue
        if low == "/game":
            chosen = _prompt_game_choice(session)
            if not chosen:
                continue
            session.select_game(chosen)
            print("\n  Chat history cleared.\n")
            _print_game_header(session.game_name or "")
            continue

        t0 = time.perf_counter()
        sources, streamer = session.ask_stream(q)

        print()
        print("SpielBot: ", end="", flush=True)
        full_answer = ""
        gen_response = None
        try:
            while True:
                token = next(streamer)
                print(token, end="", flush=True)
                full_answer += token
        except StopIteration as e:
            gen_response = e.value
        print("\n")

        t1 = time.perf_counter()

        if verbose:
            print(f"\n[verbose] retrieval+generate: {(t1 - t0):.2f}s")
            if sources:
                print("\n--- Context ---\n")
                print(format_context(sources))
                print("\n--- End context ---\n")

        if gen_response and gen_response.error:
            print(f"Error: {gen_response.error}\n")
        elif gen_response and sources and not gen_response.error:
            session.commit_to_history(q, gen_response.answer)

        _print_sources(sources, show_sources)


def _run_single_query(
    session: SpielBotSession,
    game: str,
    query: str,
    verbose: bool,
    show_sources: bool,
) -> None:
    session.select_game(game)
    t0 = time.perf_counter()
    result = session.ask(query)
    t1 = time.perf_counter()
    if verbose:
        print(f"[verbose] retrieval+generate: {(t1 - t0):.2f}s")
        if result.sources:
            print("\n--- Retrieved chunks ---")
            from retrieve import _format_result_header

            for i, r in enumerate(result.sources, 1):
                print(_format_result_header(i, r))
            print("\n--- Context ---\n")
            print(format_context(result.sources))
            print("\n--- End context ---\n")
    _print_answer(result, show_sources)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SpielBot orchestrator — interactive or single-query mode.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Game selection + chat loop.",
    )
    parser.add_argument("--game", type=str, default=None)
    parser.add_argument("--query", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print retrieval details, context, and timing.",
    )
    parser.add_argument(
        "--show-sources",
        action="store_true",
        help="Print source details after the answer.",
    )
    args = parser.parse_args()

    if args.interactive:
        session = SpielBotSession(
            model=args.model,
            temperature=args.temperature,
            eager_load=True,
        )
        _interactive_loop(session, args.show_sources, args.verbose)
        return

    if not args.game or args.query is None:
        parser.error("Single-query mode requires --game and --query.")

    if args.game not in GAMES:
        print(
            f"Unknown game '{args.game}'. Valid: {', '.join(GAMES.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)

    session = SpielBotSession(
        model=args.model,
        temperature=args.temperature,
        eager_load=True,
    )
    _run_single_query(
        session,
        args.game,
        args.query,
        args.verbose,
        args.show_sources,
    )


if __name__ == "__main__":
    main()
