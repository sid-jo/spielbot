import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Paperclip, Send, X, Menu, type LucideProps } from "lucide-react";
import type { Game, MockSource } from "@/lib/games";
import { ChatSidebar } from "@/components/ChatSidebar";
import { SourceCitations } from "@/components/SourceCitations";
import { gameBanner, gameMotif } from "@/lib/gameAssets";
import { SpielbotOracle } from "@/components/SpielbotOracle";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  image?: string;
  sources?: MockSource[];
  timestamp: Date;
}

interface ChatWindowProps {
  game: Game;
}

export function ChatWindow({ game }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isThinking]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPendingImage(reader.result as string);
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const resetChat = () => {
    setMessages([]);
    setPendingImage(null);
    setInput("");
    setIsThinking(false);
    setStreamingId(null);
  };

  const send = (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text && !pendingImage) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text || "What do you make of this?",
      image: pendingImage ?? undefined,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    const hadImage = !!pendingImage;
    setPendingImage(null);
    setIsThinking(true);

    // Mocked assistant response — shown with a graceful line-by-line reveal.
    window.setTimeout(() => {
      const fullAnswer = hadImage
        ? `Based on the board state you shared, here's what I see for **${game.name}**:\n\n` +
          `This is a preview UI showing how SpielBot will respond. Once connected to the backend, you'll get a real, source-grounded analysis of your board photo with specific rule citations.`
        : `Great question about **${game.name}**!\n\n` +
          `Here's a placeholder answer with **markdown** support:\n\n` +
          `- Bullet points work\n- Bold and *italic* render correctly\n- \`inline code\` too\n\n` +
          `Connect SpielBot to the backend to get real, retrieval-grounded answers with citations.`;

      const assistantId = crypto.randomUUID();
      const estimatedLineCount = Math.max(3, fullAnswer.split(/\n+/).filter(Boolean).length + 2);
      const revealDuration = Math.max(900, estimatedLineCount * 180);

      setIsThinking(false);
      setStreamingId(assistantId);
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: fullAnswer,
          sources: game.mockSources,
          timestamp: new Date(),
        },
      ]);

      window.setTimeout(() => {
        setStreamingId((current) => (current === assistantId ? null : current));
      }, revealDuration);
    }, 900);
  };

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* Sidebar — desktop */}
      <div className="hidden w-72 shrink-0 border-r border-green-dark/20 lg:block">
        <ChatSidebar game={game} onNewChat={resetChat} />
      </div>

      {/* Sidebar — mobile drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="absolute left-0 top-0 h-full w-72 shadow-lift">
            <ChatSidebar
              game={game}
              onNewChat={() => {
                resetChat();
                setSidebarOpen(false);
              }}
              onClose={() => setSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Chat area */}
      <div className="relative flex flex-1 flex-col">
        {/* Game-themed motif backdrop (very subtle) */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage: gameMotif[game.id],
            backgroundSize: "140px",
          }}
        />

        {/* Game banner — full-width hero strip atop the chat area */}
        <div
          className="relative h-24 w-full overflow-hidden border-b sm:h-32"
          style={{ borderBottomColor: `${game.accentHex}40` }}
        >
          <img
            src={gameBanner[game.id]}
            alt={`${game.name} key art`}
            className="absolute inset-0 h-full w-full object-cover"
          />
          {/* Bottom fade so it blends into the chat surface */}
          <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-cream to-transparent" />
          {/* Mobile-only menu + title overlay */}
          <div className="absolute inset-0 flex items-center justify-between px-4 lg:hidden">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-md bg-cream/90 p-1.5 text-text-dark shadow-soft transition-smooth hover:bg-cream"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <span
              className="rounded-md bg-cream/90 px-2.5 py-1 font-display text-sm font-semibold text-text-dark shadow-soft"
              style={{ boxShadow: `0 2px 8px -2px ${game.accentHex}66` }}
            >
              {game.name}
            </span>
          </div>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="relative flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6">
            {messages.length === 0 && !isThinking && (
              <EmptyState game={game} onPick={(p) => send(p)} />
            )}

            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                isStreaming={streamingId === m.id}
                game={game}
              />
            ))}

            {isThinking && <TypingIndicator game={game} />}
          </div>
        </div>

        {/* Composer */}
        <div className="relative border-t border-border bg-cream/85 backdrop-blur-md">
          <div className="mx-auto max-w-3xl px-4 py-3 sm:px-6">
            {pendingImage && (
              <div className="mb-2 flex items-center gap-3 rounded-lg border border-tan bg-card p-2">
                <img
                  src={pendingImage}
                  alt="Pending upload"
                  className="h-14 w-14 rounded-md object-cover"
                />
                <div className="flex-1 text-xs text-text-muted">
                  Image attached. Add a question and hit send.
                </div>
                <button
                  onClick={() => setPendingImage(null)}
                  className="rounded-md p-1.5 text-text-muted transition-smooth hover:bg-tan/40 hover:text-text-dark"
                  aria-label="Remove image"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            <div className="flex items-end gap-2 rounded-xl border-2 border-tan bg-cream p-2 transition-smooth focus-within:border-green-sage">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex h-9 w-9 items-center justify-center rounded-md text-text-muted transition-smooth hover:bg-tan/50 hover:text-green-dark"
                aria-label="Attach image"
                title="Attach image"
              >
                <Paperclip className="h-4.5 w-4.5" />
              </button>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Ask a rules question..."
                rows={1}
                className="flex-1 resize-none bg-transparent px-1 py-2 text-sm text-text-dark placeholder:text-text-muted/70 focus:outline-none"
              />

              <button
                onClick={() => send()}
                disabled={(!input.trim() && !pendingImage) || isThinking}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-green-dark text-cream transition-smooth hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-30"
                aria-label="Send"
              >
                <Send className="h-4 w-4" />
              </button>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={handleFile}
                className="hidden"
              />
            </div>

            <p className="mt-2 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted/70">
              Enter to send · Shift + Enter for newline
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState({
  game,
  onPick,
}: {
  game: Game;
  onPick: (p: string) => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      {/* Hero artwork — game banner with oracle peeking in */}
      <div
        className="relative mb-5 w-full max-w-md overflow-hidden rounded-2xl border-2 shadow-card"
        style={{ borderColor: `${game.accentHex}55` }}
      >
        <img
          src={gameBanner[game.id]}
          alt={`${game.name} key art`}
          className="h-36 w-full object-cover"
        />
        <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-cream via-cream/60 to-transparent" />
        <div className="absolute -bottom-1 left-1/2 -translate-x-1/2">
          <div
            className="rounded-full bg-cream p-1.5 shadow-lift"
            style={{ boxShadow: `0 8px 20px -8px ${game.accentHex}99` }}
          >
            <SpielbotOracle size={56} idleLook trackCursor accent={game.accentHex} />
          </div>
        </div>
      </div>
      <h2 className="mt-6 font-display text-2xl font-bold text-text-dark">
        Ask me anything about{" "}
        <span style={{ color: game.accentHex }}>{game.name}</span> rules
      </h2>
      <p className="mt-2 text-sm text-text-muted">
        Try one of these to get started:
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {game.starterPrompts.map((p) => (
          <button
            key={p}
            onClick={() => onPick(p)}
            className="rounded-full border border-tan bg-card px-4 py-2 text-sm text-text-dark shadow-soft transition-smooth hover:-translate-y-0.5 hover:shadow-card"
            onMouseEnter={(e) =>
              (e.currentTarget.style.borderColor = game.accentHex)
            }
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "")}
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

function TypingIndicator({ game }: { game: Game }) {
  return (
    <div className="flex items-end gap-2.5 animate-float-up">
      <BotAvatar game={game} thinking />
      <div
        className="rounded-xl rounded-bl-sm border-l-[3px] bg-card px-4 py-3 shadow-soft"
        style={{ borderLeftColor: game.accentHex }}
      >
        <div className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full animate-pulse-dot"
            style={{ background: game.accentHex }}
          />
          <span
            className="h-2 w-2 rounded-full animate-pulse-dot"
            style={{ background: game.accentHex, animationDelay: "0.2s" }}
          />
          <span
            className="h-2 w-2 rounded-full animate-pulse-dot"
            style={{ background: game.accentHex, animationDelay: "0.4s" }}
          />
        </div>
      </div>
    </div>
  );
}

function BotAvatar({ game, thinking = false }: { game: Game; thinking?: boolean }) {
  return (
    <div
      className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-cream"
      style={{
        boxShadow: `inset 0 0 0 1.5px ${game.accentHex}55, 0 2px 8px -2px ${game.accentHex}40`,
      }}
      aria-label="SpielBot"
    >
      <SpielbotOracle
        size={28}
        thinking={thinking}
        idleLook={!thinking}
        accent={game.accentHex}
      />
    </div>
  );
}

function MeepleIcon(props: LucideProps) {
  // Classic meeple silhouette — head, outstretched arms, splayed legs.
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      {...props}
    >
      <path d="M12 2.4c-1.6 0-2.9 1.3-2.9 2.9 0 1.1.6 2.1 1.5 2.6-1 .3-2 .7-3 1.2-1.6.8-3 1.7-3.4 2.7-.3.8.1 1.6.9 2 .6.3 1.3.2 1.9-.2.7-.5 1.5-1 2.4-1.4-.4 1.4-.9 3.1-1.4 4.7-.4 1.4-.8 2.7-.9 3.4-.1.7.4 1.3 1.1 1.4h2.6c.6 0 1.1-.4 1.2-1l.9-3.6c.1-.4.6-.4.7 0l.9 3.6c.1.6.6 1 1.2 1h2.6c.7-.1 1.2-.7 1.1-1.4-.1-.7-.5-2-.9-3.4-.5-1.6-1-3.3-1.4-4.7.9.4 1.7.9 2.4 1.4.6.4 1.3.5 1.9.2.8-.4 1.2-1.2.9-2-.4-1-1.8-1.9-3.4-2.7-1-.5-2-.9-3-1.2.9-.5 1.5-1.5 1.5-2.6 0-1.6-1.3-2.9-2.9-2.9z" />
    </svg>
  );
}

function UserAvatar() {
  return (
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-tan text-green-dark shadow-soft">
      <MeepleIcon className="h-5 w-5" />
    </div>
  );
}

function AssistantMessageContent({
  content,
  isStreaming,
}: {
  content: string;
  isStreaming: boolean;
}) {
  const blocks = content
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className="prose-sm">
      {blocks.map((block, index) => {
        const isList = /^[-*]\s|^\d+\.\s/m.test(block);
        return (
          <div
            key={`${index}-${block.slice(0, 24)}`}
            className={isStreaming ? "reveal-line" : undefined}
            style={
              isStreaming
                ? { animationDelay: `${index * 140}ms`, animationFillMode: "forwards" }
                : undefined
            }
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => (
                  <p className="mb-2 last:mb-0">{children}</p>
                ),
                ul: ({ children }) => (
                  <ul className="mb-2 ml-4 list-disc space-y-1 last:mb-0">
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol className="mb-2 ml-4 list-decimal space-y-1 last:mb-0">
                    {children}
                  </ol>
                ),
                strong: ({ children }) => (
                  <strong className="font-semibold text-green-dark">
                    {children}
                  </strong>
                ),
                code: ({ children }) => (
                  <code className="rounded bg-cream px-1 py-0.5 font-mono text-[12px] text-green-dark">
                    {children}
                  </code>
                ),
              }}
            >
              {block}
            </ReactMarkdown>
            {!isList && index < blocks.length - 1 && <div className="h-1" />}
          </div>
        );
      })}
      {isStreaming && (
        <span className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse bg-green-sage" />
      )}
    </div>
  );
}

function MessageBubble({
  message,
  isStreaming,
  game,
}: {
  message: Message;
  isStreaming: boolean;
  game: Game;
}) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex items-end gap-2.5 animate-float-up ${
        isUser ? "flex-row-reverse" : ""
      }`}
    >
      {isUser ? <UserAvatar /> : <BotAvatar game={game} thinking={isStreaming} />}

      <div className={`flex max-w-[82%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-xl px-4 py-3 text-sm leading-relaxed shadow-soft ${
            isUser
              ? "rounded-br-sm bg-tan text-text-dark"
              : "rounded-bl-sm border-l-[3px] bg-card text-text-dark"
          }`}
          style={!isUser ? { borderLeftColor: game.accentHex } : undefined}
        >
          {message.image && (
            <img
              src={message.image}
              alt="Board state"
              className="mb-2 max-h-72 rounded-md object-cover"
            />
          )}
          {isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            <AssistantMessageContent content={message.content} isStreaming={isStreaming} />
          )}
        </div>

        {!isUser && !isStreaming && message.sources && (
          <SourceCitations sources={message.sources} />
        )}
      </div>
    </div>
  );
}
