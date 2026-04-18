"""
SpielBot — Streamlit UI

Run with: streamlit run app.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

from orchestrator import SpielBotSession  # noqa: E402

st.set_page_config(
    page_title="SpielBot",
    page_icon="🎲",
    layout="centered",
    initial_sidebar_state="expanded",
)

GAME_INFO = {
    "catan": {
        "label": "Catan",
        "tagline": "Trade, build, settle the island",
        "icon": "assets/catan_icon.svg",
        "emoji": "🏝️",
    },
    "splendor": {
        "label": "Splendor",
        "tagline": "Collect gems, acquire cards, attract nobles",
        "icon": "assets/splendor_icon.svg",
        "emoji": "💎",
    },
    "root": {
        "label": "Root",
        "tagline": "Asymmetric woodland warfare",
        "icon": "assets/root_icon.svg",
        "emoji": "🦊",
    },
}


# ═════════════════════════════════════════════════════════════════════════
# CUSTOM CSS
# ═════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
    :root {
        --green-dark: #546B41;
        --green-sage: #99AD7A;
        --tan: #DCCCAC;
        --cream: #FFF8EC;
        --text-dark: #2D3A24;
        --text-muted: #6B7B5E;
    }

    .stApp {
        background-color: var(--cream);
    }

    section[data-testid="stSidebar"] {
        background-color: var(--green-dark);
    }
    section[data-testid="stSidebar"] * {
        color: var(--cream) !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        background-color: var(--green-sage);
        color: var(--cream) !important;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: background-color 0.2s;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background-color: var(--tan);
        color: var(--green-dark) !important;
    }

    .stChatMessage[data-testid="stChatMessage"]:has(
        [data-testid="stChatMessageAvatarUser"]
    ) {
        background-color: var(--tan);
        border-radius: 12px;
        margin: 4px 0;
    }
    .stChatMessage[data-testid="stChatMessage"]:has(
        [data-testid="stChatMessageAvatarAssistant"]
    ) {
        background-color: white;
        border-left: 3px solid var(--green-sage);
        border-radius: 0 12px 12px 0;
        margin: 4px 0;
    }

    .stChatInput > div {
        border-color: var(--green-sage) !important;
        border-radius: 12px;
    }
    .stChatInput textarea {
        background-color: white;
    }

    .stButton > button {
        border-radius: 8px;
        border: 2px solid var(--green-dark);
        color: var(--green-dark);
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        background-color: var(--green-dark);
        color: var(--cream);
    }

    .streamlit-expanderHeader {
        background-color: var(--tan) !important;
        border-radius: 8px;
        font-weight: 600;
        color: var(--green-dark) !important;
    }
    .streamlit-expanderContent {
        background-color: white;
        border: 1px solid var(--tan);
        border-radius: 0 0 8px 8px;
    }

    .source-card {
        background: var(--cream);
        border-left: 3px solid var(--green-sage);
        padding: 10px 14px;
        margin: 6px 0;
        border-radius: 0 8px 8px 0;
        font-size: 0.88em;
        line-height: 1.5;
    }
    .source-card .source-header {
        font-weight: 700;
        color: var(--green-dark);
        margin-bottom: 4px;
    }
    .source-card .source-body {
        color: var(--text-muted);
    }

    .stFileUploader {
        border-radius: 8px;
    }
    .stFileUploader > div {
        border-color: var(--green-sage) !important;
    }

    .game-card {
        background: white;
        border: 2px solid var(--tan);
        border-radius: 16px;
        padding: 24px 20px;
        text-align: center;
        transition: all 0.25s ease;
        cursor: pointer;
    }
    .game-card:hover {
        border-color: var(--green-dark);
        box-shadow: 0 4px 16px rgba(84, 107, 65, 0.15);
        transform: translateY(-2px);
    }
    .game-card .game-emoji {
        font-size: 2.5em;
        margin-bottom: 8px;
    }
    .game-card .game-name {
        font-size: 1.3em;
        font-weight: 700;
        color: var(--green-dark);
        margin-bottom: 4px;
    }
    .game-card .game-tagline {
        font-size: 0.9em;
        color: var(--text-muted);
    }

    .stSpinner > div {
        border-top-color: var(--green-dark) !important;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {
        background: var(--cream);
    }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ═════════════════════════════════════════════════════════════════════════

if "session" not in st.session_state:
    st.session_state.session = None
    st.session_state.messages = []
    st.session_state.game = None
    # Image stays attached across queries until the user removes it,
    # switches games, or closes the app.
    st.session_state.attached_image = None
    # Bumped to force the file_uploader widget to reset (clearing the
    # visible "drop file" state in the UI).
    st.session_state.upload_counter = 0
    st.session_state.indexes_loaded = False


@st.cache_resource(show_spinner=False)
def load_session() -> SpielBotSession:
    """Load SpielBotSession with all indexes. Cached across reruns."""
    return SpielBotSession(eager_load=True)


# ═════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════

def render_source_card(i: int, src) -> str:
    """Build HTML for one source citation card."""
    if src.source_type == "rulebook":
        icon = "📖"
        title = src.section_title or "Rulebook"
        if src.page_start > 0:
            if src.page_start == src.page_end:
                title += f" (p.{src.page_start})"
            else:
                title += f" (pp.{src.page_start}-{src.page_end})"
    elif src.source_type == "card":
        icon = "🃏"
        title = src.section_title or "Card"
        if src.card_suit:
            title += f" [{src.card_suit}]"
    else:
        icon = "💬"
        title = src.thread_subject or "Forum Thread"
        if src.resolution_status:
            title += f" ({src.resolution_status})"

    body = src.content
    if len(body) > 250:
        body = body[:250].rsplit(" ", 1)[0] + "..."
    body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return (
        f'<div class="source-card">'
        f'<div class="source-header">{icon} [{i}] {title}</div>'
        f'<div class="source-body">{body}</div>'
        f'</div>'
    )


def select_game(game_key: str) -> None:
    """Handle game selection. Resets chat and configures session."""
    session = load_session()
    session.select_game(game_key)
    st.session_state.session = session
    st.session_state.game = game_key
    st.session_state.messages = []
    st.session_state.attached_image = None
    st.session_state.upload_counter += 1
    st.session_state.indexes_loaded = True


def clear_attached_image() -> None:
    """Remove the sticky image and reset the uploader widget."""
    st.session_state.attached_image = None
    st.session_state.upload_counter += 1


# ═════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════════════════════

with st.sidebar:
    logo_path = Path(__file__).parent / "assets" / "spielbot_logo.svg"
    if logo_path.exists():
        st.image(str(logo_path), width=200)
    else:
        st.markdown("## 🎲 SpielBot")

    st.markdown("*Your board game rules assistant*")
    st.divider()

    if st.session_state.game:
        info = GAME_INFO[st.session_state.game]
        st.markdown(f"### {info['emoji']} Playing: {info['label']}")
        st.caption(info["tagline"])
        st.divider()

        if st.button("🗑️ New Chat", use_container_width=True):
            st.session_state.messages = []
            session = load_session()
            session.reset_chat()
            st.rerun()

        if st.button("🔄 Switch Game", use_container_width=True):
            st.session_state.game = None
            st.session_state.messages = []
            clear_attached_image()
            st.rerun()

    st.divider()

    with st.expander("ℹ️ About SpielBot"):
        st.markdown("""
        SpielBot answers board game rules questions using
        retrieval-augmented generation over official rulebooks
        and BoardGameGeek community discussions.

        **Features:**
        - 📖 Grounded in official rules + community wisdom
        - 📷 Upload a photo of your game state
        - 📑 Source citations for every answer
        - 🔍 Multi-query retrieval for thorough coverage

        **Supported games:** Catan, Splendor, Root
        """)


# ═════════════════════════════════════════════════════════════════════════
# MAIN CONTENT — GAME SELECTION
# ═════════════════════════════════════════════════════════════════════════

if st.session_state.game is None:
    st.markdown(
        '<h1 style="text-align:center; color:#546B41; margin-top:40px;">'
        '🎲 Welcome to SpielBot</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align:center; color:#6B7B5E; font-size:1.1em; '
        'margin-bottom:40px;">'
        'Select a game to get started</p>',
        unsafe_allow_html=True,
    )

    if not st.session_state.indexes_loaded:
        with st.spinner("Loading SpielBot indexes (first time only)..."):
            load_session()
            st.session_state.indexes_loaded = True

    cols = st.columns(3, gap="large")
    for i, (game_key, info) in enumerate(GAME_INFO.items()):
        with cols[i]:
            icon_path = Path(__file__).parent / info["icon"]
            if icon_path.exists():
                st.image(str(icon_path), width=80)
            else:
                st.markdown(
                    f'<div style="font-size:3em; text-align:center;">'
                    f'{info["emoji"]}</div>',
                    unsafe_allow_html=True,
                )

            if st.button(
                f'{info["label"]}',
                key=f"select_{game_key}",
                use_container_width=True,
            ):
                select_game(game_key)
                st.rerun()

            st.caption(info["tagline"])

    st.stop()


# ═════════════════════════════════════════════════════════════════════════
# MAIN CONTENT — CHAT INTERFACE
# ═════════════════════════════════════════════════════════════════════════

game_info = GAME_INFO[st.session_state.game]

st.markdown(
    f'<h2 style="color:#546B41; margin-bottom:0;">'
    f'{game_info["emoji"]} {game_info["label"]}</h2>',
    unsafe_allow_html=True,
)
st.caption(f"Ask anything about {game_info['label']} rules")

# ── Display chat history ──
for msg in st.session_state.messages:
    with st.chat_message(
        msg["role"],
        avatar="🎲" if msg["role"] == "assistant" else None,
    ):
        st.markdown(msg["content"])

        if msg.get("sub_questions"):
            with st.expander(
                f"🔍 Search queries ({len(msg['sub_questions'])})",
                expanded=False,
            ):
                for j, sq in enumerate(msg["sub_questions"], 1):
                    st.markdown(f"{j}. {sq}")

        if msg.get("sources"):
            with st.expander(
                f"📑 Sources ({len(msg['sources'])} retrieved)",
                expanded=False,
            ):
                html_parts = [
                    render_source_card(j, src)
                    for j, src in enumerate(msg["sources"], 1)
                ]
                st.markdown("\n".join(html_parts), unsafe_allow_html=True)

# ── Image upload area ──
# The widget's key includes `upload_counter` so that clearing the image
# (via Remove Image or Switch Game) resets the uploader visually. The
# uploaded image itself is "sticky" — it stays attached to every query
# until explicitly removed, the game is switched, or the app is closed.
uploaded_file = st.file_uploader(
    "📷 Attach a photo of your game state",
    type=["jpg", "jpeg", "png", "webp"],
    key=f"image_upload_{st.session_state.upload_counter}",
    label_visibility="collapsed",
    help="Upload a photo to ask questions about your current board state",
)

if uploaded_file is not None:
    st.session_state.attached_image = uploaded_file.getvalue()

if st.session_state.attached_image is not None:
    preview_cols = st.columns([1, 4])
    with preview_cols[0]:
        st.image(
            st.session_state.attached_image,
            width=100,
            caption="Attached",
        )
    with preview_cols[1]:
        st.caption(
            "📷 Image attached — it will be sent with every question "
            "until you remove it or switch games"
        )
        if st.button("✕ Remove image", key="remove_image"):
            clear_attached_image()
            st.rerun()


# ── Chat input ──
if prompt := st.chat_input(f"Ask about {game_info['label']} rules..."):
    image_bytes = st.session_state.attached_image

    user_msg = {"role": "user", "content": prompt}
    st.session_state.messages.append(user_msg)

    with st.chat_message("user"):
        st.markdown(prompt)
        if image_bytes:
            st.image(image_bytes, width=200, caption="Attached photo")

    with st.chat_message("assistant", avatar="🎲"):

        with st.status(
            "🔍 Analyzing your question...",
            expanded=False,
        ) as status:
            session = load_session()

            t0 = time.time()
            result = session.ask(prompt, image=image_bytes)
            elapsed = time.time() - t0

            if result.reasoning and result.reasoning.sub_questions:
                n_q = len(result.reasoning.sub_questions)
                n_s = len(result.sources)
                status.update(
                    label=(
                        f"✅ Found {n_s} sources via {n_q} queries "
                        f"({elapsed:.1f}s)"
                    ),
                    state="complete",
                )
            else:
                status.update(label="✅ Done", state="complete")

        if result.error:
            st.error(f"Error: {result.error}")
        else:
            st.markdown(result.answer)

        if result.reasoning and result.reasoning.sub_questions:
            with st.expander(
                f"🔍 Search queries ({len(result.reasoning.sub_questions)})",
                expanded=False,
            ):
                for j, sq in enumerate(result.reasoning.sub_questions, 1):
                    st.markdown(f"{j}. {sq}")

        if result.sources:
            with st.expander(
                f"📑 Sources ({len(result.sources)} retrieved)",
                expanded=False,
            ):
                html_parts = [
                    render_source_card(j, src)
                    for j, src in enumerate(result.sources, 1)
                ]
                st.markdown("\n".join(html_parts), unsafe_allow_html=True)

    assistant_msg = {
        "role": "assistant",
        "content": (
            result.answer
            if not result.error
            else f"Error: {result.error}"
        ),
        "sources": result.sources if result.sources else None,
        "sub_questions": (
            result.reasoning.sub_questions
            if result.reasoning and result.reasoning.sub_questions
            else None
        ),
    }
    st.session_state.messages.append(assistant_msg)

    # NOTE: session.ask() already appends to the session's history
    # internally, so we intentionally do NOT call commit_to_history here.
    # (Only ask_stream() requires an explicit commit.)
