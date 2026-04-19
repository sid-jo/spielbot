import { useEffect, useRef, useState } from "react";

interface SpielbotOracleProps {
  /** Pixel size of the rendered oracle. */
  size?: number;
  /** When true, the eye darts around playfully (used while generating). */
  thinking?: boolean;
  /** When true, the eye gently looks side-to-side (used at idle). */
  idleLook?: boolean;
  /** When true, the eye tracks the user's cursor across the viewport. */
  trackCursor?: boolean;
  /** Optional accent color used for the subtle outer aura. */
  accent?: string;
  className?: string;
  title?: string;
}

/**
 * SpielBot — a playful green D20 die with a single curious, all-seeing eye.
 *
 * Rendered as a stylized icosahedron in 3/4 perspective with shaded triangular
 * facets to give it real depth. A handful of face numbers sit on surrounding
 * facets so it clearly reads as a 20-sided die. The eye stays fully open
 * (no eyelid visible) and blinks occasionally for personality.
 */
export function SpielbotOracle({
  size = 64,
  thinking = false,
  idleLook = true,
  trackCursor = false,
  accent,
  className,
  title = "SpielBot oracle",
}: SpielbotOracleProps) {
  // Pupil offset in local SVG units. Front face center is roughly (32, 36).
  const [pupil, setPupil] = useState({ x: 0, y: 0 });
  const [blink, setBlink] = useState(false);
  const mounted = useRef(true);
  const wrapperRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Cursor tracking — wins over thinking/idle when active and cursor is on screen.
  useEffect(() => {
    if (!trackCursor || thinking) return;

    const onMove = (e: MouseEvent) => {
      const el = wrapperRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.hypot(dx, dy) || 1;
      const maxR = 3;
      const r = Math.min(maxR, (dist / 220) * maxR);
      setPupil({ x: (dx / dist) * r, y: (dy / dist) * r * 0.9 });
    };

    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, [trackCursor, thinking]);

  // Eye-darting / idle glance behavior. Disabled when actively cursor-tracking.
  useEffect(() => {
    if (trackCursor && !thinking) return;
    if (!thinking && !idleLook) {
      setPupil({ x: 0, y: 0 });
      return;
    }

    let timeoutId: number;
    const scheduleNext = () => {
      const interval = thinking
        ? 360 + Math.random() * 320
        : 1600 + Math.random() * 1800;
      timeoutId = window.setTimeout(() => {
        if (!mounted.current) return;
        const radius = thinking ? 3 : 1.6;
        const angle = Math.random() * Math.PI * 2;
        const r = radius * (0.55 + Math.random() * 0.45);
        setPupil({ x: Math.cos(angle) * r, y: Math.sin(angle) * r * 0.85 });
        scheduleNext();
      }, interval);
    };
    scheduleNext();
    return () => window.clearTimeout(timeoutId);
  }, [thinking, idleLook, trackCursor]);

  // Blink loop — eyelid only appears for the brief blink frames.
  useEffect(() => {
    let blinkTimeout: number;
    let closeTimeout: number;
    const scheduleBlink = () => {
      blinkTimeout = window.setTimeout(
        () => {
          if (!mounted.current) return;
          setBlink(true);
          closeTimeout = window.setTimeout(() => {
            if (!mounted.current) return;
            setBlink(false);
            scheduleBlink();
          }, 140);
        },
        2800 + Math.random() * 3200,
      );
    };
    scheduleBlink();
    return () => {
      window.clearTimeout(blinkTimeout);
      window.clearTimeout(closeTimeout);
    };
  }, []);

  const accentColor = accent ?? "#99AD7A";

  return (
    <span
      ref={wrapperRef}
      className={className}
      style={{
        display: "inline-block",
        width: size,
        height: size,
        lineHeight: 0,
      }}
      aria-label={title}
      role="img"
    >
      <svg
        viewBox="0 0 64 64"
        width={size}
        height={size}
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/*
            Per-facet gradients designed so adjacent triangles have noticeably
            different luminance — this is what sells the 3D icosahedron read.
            Light source is upper-left.
          */}
          <linearGradient id="d20Front" x1="0.2" y1="0" x2="0.8" y2="1">
            <stop offset="0%" stopColor="#A7C281" />
            <stop offset="100%" stopColor="#5E7A45" />
          </linearGradient>
          <linearGradient id="d20TopLeft" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#B8D192" />
            <stop offset="100%" stopColor="#7A9658" />
          </linearGradient>
          <linearGradient id="d20TopMid" x1="0.5" y1="0" x2="0.5" y2="1">
            <stop offset="0%" stopColor="#9AB875" />
            <stop offset="100%" stopColor="#6B8A4E" />
          </linearGradient>
          <linearGradient id="d20TopRight" x1="1" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#7E9A5B" />
            <stop offset="100%" stopColor="#506B38" />
          </linearGradient>
          <linearGradient id="d20Right" x1="1" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5E7A42" />
            <stop offset="100%" stopColor="#374B26" />
          </linearGradient>
          <linearGradient id="d20BotRight" x1="1" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="#34471F" />
            <stop offset="100%" stopColor="#5A7640" />
          </linearGradient>
          <linearGradient id="d20BotLeft" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#3D5226" />
            <stop offset="100%" stopColor="#637E48" />
          </linearGradient>
          <linearGradient id="d20Left" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#88A664" />
            <stop offset="100%" stopColor="#536F3B" />
          </linearGradient>
          <linearGradient id="d20BotMidL" x1="0.5" y1="0" x2="0.5" y2="1">
            <stop offset="0%" stopColor="#4E6831" />
            <stop offset="100%" stopColor="#2C3C19" />
          </linearGradient>
          <linearGradient id="d20BotMidR" x1="0.5" y1="0" x2="0.5" y2="1">
            <stop offset="0%" stopColor="#445A2A" />
            <stop offset="100%" stopColor="#263416" />
          </linearGradient>
          <radialGradient id="frontHighlight" cx="0.4" cy="0.3" r="0.7">
            <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="auraGlow" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%" stopColor={accentColor} stopOpacity="0.55" />
            <stop offset="70%" stopColor={accentColor} stopOpacity="0" />
          </radialGradient>
          <filter id="d20Shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="0.6" />
          </filter>
        </defs>

        {thinking && (
          <circle
            cx="32"
            cy="32"
            r="30"
            fill="url(#auraGlow)"
            style={{
              transformOrigin: "32px 32px",
              animation: "spielbotPulse 1.4s ease-in-out infinite",
            }}
          />
        )}

        {/* Soft contact shadow under the die */}
        <ellipse
          cx="32"
          cy="60"
          rx="20"
          ry="2.4"
          fill="#000"
          opacity="0.18"
          filter="url(#d20Shadow)"
        />

        {/*
          Icosahedron in 3/4 view. Vertices:
            T   (32, 3)   — top apex
            TL  (8, 18)   TR (56, 18)
            ML  (4, 36)   MR (60, 36)
            BL  (16, 54)  BR (48, 54)
            B   (32, 61)  — bottom apex
          Inner ring (front facet vertices):
            IL  (20, 28)  IR (44, 28)  IB (32, 50)
        */}

        {/* --- Top cap (3 facets meeting at apex) --- */}
        <polygon
          points="32,3 8,18 20,28"
          fill="url(#d20TopLeft)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <polygon
          points="32,3 20,28 44,28"
          fill="url(#d20TopMid)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <polygon
          points="32,3 44,28 56,18"
          fill="url(#d20TopRight)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />

        {/* --- Upper side facets --- */}
        <polygon
          points="8,18 4,36 20,28"
          fill="url(#d20Left)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <polygon
          points="56,18 60,36 44,28"
          fill="url(#d20Right)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />

        {/* --- Mid-left & mid-right wedges connecting to bottom corners --- */}
        <polygon
          points="4,36 16,54 20,28"
          fill="url(#d20Left)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <polygon
          points="60,36 48,54 44,28"
          fill="url(#d20Right)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />

        {/* --- Bottom cap (4 facets) --- */}
        <polygon
          points="16,54 32,50 20,28"
          fill="url(#d20BotLeft)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <polygon
          points="48,54 44,28 32,50"
          fill="url(#d20BotRight)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <polygon
          points="16,54 32,61 32,50"
          fill="url(#d20BotMidL)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />
        <polygon
          points="32,50 32,61 48,54"
          fill="url(#d20BotMidR)"
          stroke="#1F2C16"
          strokeWidth="0.6"
          strokeLinejoin="round"
        />

        {/* --- Front facet — the bright triangle holding the eye --- */}
        <polygon
          points="20,28 44,28 32,50"
          fill="url(#d20Front)"
          stroke="#1A2511"
          strokeWidth="0.9"
          strokeLinejoin="round"
        />
        <polygon
          points="20,28 44,28 32,50"
          fill="url(#frontHighlight)"
          pointerEvents="none"
        />

        {/* Visible face numbers — etched into surrounding facets */}
        <g
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontWeight="700"
          fill="#FFF8EC"
          opacity="0.78"
          textAnchor="middle"
        >
          <text x="32" y="17" fontSize="5.5">20</text>
          <text x="13" y="24" fontSize="4">7</text>
          <text x="51" y="24" fontSize="4">13</text>
          <text x="11" y="40" fontSize="3.6">2</text>
          <text x="53" y="40" fontSize="3.6">17</text>
          <text x="22" y="50" fontSize="3.4">5</text>
          <text x="42" y="50" fontSize="3.4">11</text>
        </g>

        {/* Eye — sits on the bright front facet, fully open */}
        <g transform="translate(32 37)">
          {/* Sclera */}
          <ellipse
            cx="0"
            cy="0"
            rx="8.5"
            ry="6.6"
            fill="#FFF8EC"
            stroke="#1F2C16"
            strokeWidth="1"
          />
          {/* Iris + pupil */}
          <g
            style={{
              transform: `translate(${pupil.x}px, ${pupil.y}px)`,
              transition: "transform 220ms cubic-bezier(0.34, 1.56, 0.64, 1)",
            }}
          >
            <circle cx="0" cy="0" r="3.6" fill="#3F5530" />
            <circle cx="0" cy="0" r="2.1" fill="#0F1A09" />
            <circle cx="-1.1" cy="-1.2" r="0.9" fill="#FFF8EC" />
            <circle cx="1.3" cy="1.0" r="0.4" fill="#FFF8EC" opacity="0.7" />
          </g>
          {/* Eyelid — only visible during a blink. Clipped to sclera shape. */}
          <clipPath id="scleraClip">
            <ellipse cx="0" cy="0" rx="8.5" ry="6.6" />
          </clipPath>
          <g clipPath="url(#scleraClip)">
            <rect
              x="-9"
              y="-7"
              width="18"
              height="14"
              fill="#5E7A45"
              stroke="#1F2C16"
              strokeWidth="0.6"
              style={{
                transformOrigin: "0px -7px",
                transform: blink ? "scaleY(1)" : "scaleY(0)",
                transition: "transform 90ms ease-in-out",
              }}
            />
          </g>
        </g>

        {/* Subtle brow above the eye for personality */}
        <path
          d="M 24 27 Q 32 24 40 27"
          stroke="#1F2C16"
          strokeWidth="1.2"
          strokeLinecap="round"
          fill="none"
          opacity="0.65"
        />
      </svg>
      <style>{`
        @keyframes spielbotPulse {
          0%, 100% { transform: scale(0.92); opacity: 0.7; }
          50% { transform: scale(1.08); opacity: 1; }
        }
      `}</style>
    </span>
  );
}
