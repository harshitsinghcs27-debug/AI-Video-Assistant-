"""
AI Video Assistant — professional Streamlit UI.

Run with:
    streamlit run app.py

Wraps the existing pipeline (process_input -> transcribe_all -> summarizer /
extractors / rag_engine) exactly as-is. This file is purely a UI layer: a
clean top bar, a project overview panel, metric cards, styled tabs, and a
chat interface for the RAG chain.
"""

import os

for key in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(key, None)

import re
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

for key in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(key, None)

for secret_name in (
    "MISTRAL_API_KEY",
    "SARVAM_API_KEY",
    "WHISPER_MODEL",
    "SARVAM_STT_MODEL",
    "YOUTUBE_COOKIES",
    "YOUTUBE_COOKIES_B64",
):
    try:
        secret_value = st.secrets.get(secret_name)
    except Exception:
        secret_value = None
    if secret_value and not os.getenv(secret_name):
        os.environ[secret_name] = str(secret_value)

from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.sammarize import summarize as summarizer, generate_title
from core.extractor import extract_action_items, extract_key_decisions, extract_questions
from core.rag_engine import build_rag_chain, ask_question
from core.local_insights import (
    action_items_locally,
    answer_locally,
    decisions_locally,
    questions_locally,
    summarize_locally,
    title_locally,
)

st.set_page_config(
    page_title="AI Video Assistant",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
PRIMARY = "#2F80ED"        # blue-600 style
PRIMARY_DARK = "#1C64D1"   # deeper blue
ACCENT = "#0EA5E9"         # sky-500, used sparingly
BG_LIGHT = "#EAF4FF"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#CFE3FA"
TEXT_MUTED = "#5B7A99"
TEXT_MAIN = "#0F2A43"

st.markdown(
    f"""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
        .stApp {{ background: linear-gradient(180deg, {BG_LIGHT} 0%, #F5FAFF 100%); }}
        #MainMenu, footer {{ visibility: hidden; }}

        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(14px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes pulseDot {{
            0%   {{ box-shadow: 0 0 0 0 rgba(14,165,233,0.55); }}
            70%  {{ box-shadow: 0 0 0 8px rgba(14,165,233,0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(14,165,233,0); }}
        }}
        @keyframes bounce {{
            0%, 80%, 100% {{ transform: scale(0); opacity: 0.4; }}
            40%           {{ transform: scale(1); opacity: 1; }}
        }}
        .fade-in {{ animation: fadeInUp 0.5s ease-out both; }}

        /* Base text readability on the light background, regardless of the
           underlying Streamlit theme. Elements with their own inline style
           or class color (set below) override this via specificity. */
        .stApp, .stApp p, .stApp span, .stApp label, .stMarkdown, .stCaption {{
            color: {TEXT_MAIN};
        }}
        .stApp small, .stCaption {{ color: {TEXT_MUTED}; }}

        @keyframes floatText {{
            0%, 100% {{ transform: translateY(0px); }}
            50%      {{ transform: translateY(-5px); }}
        }}
        @keyframes glowShift {{
            0%, 100% {{ filter: drop-shadow(0 0 0px rgba(47,128,237,0)); }}
            50%      {{ filter: drop-shadow(0 0 10px rgba(14,165,233,0.35)); }}
        }}

        .topbar-grid {{
            display: grid; grid-template-columns: 1fr auto 1fr; align-items: center;
            padding-bottom: 1.1rem; border-bottom: 1px solid {CARD_BORDER}; margin-bottom: 1.6rem;
        }}
        .topbar-grid .right {{ display: flex; justify-content: flex-end; }}
        .brand-float {{
            display: inline-block; text-align: center;
            animation: floatText 3.6s ease-in-out infinite, glowShift 3.6s ease-in-out infinite;
        }}
        .brand-name {{
            font-weight: 800; font-size: 2.4rem; letter-spacing: -0.01em; line-height: 1.15;
            background: linear-gradient(120deg, {TEXT_MAIN}, {ACCENT}, {TEXT_MAIN});
            background-size: 200% auto;
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .brand-tag {{ color: {TEXT_MUTED}; font-size: 0.82rem; margin-top: 2px; }}
        .status-pill {{
            display: inline-flex; align-items: center; gap: 0.45rem;
            background: {CARD_BG}; border: 1px solid {CARD_BORDER};
            border-radius: 999px; padding: 0.35rem 0.9rem;
            color: {TEXT_MUTED}; font-size: 0.78rem; font-weight: 600;
        }}
        .status-pill .dot {{ width: 8px; height: 8px; border-radius: 50%; background: {ACCENT}; animation: pulseDot 1.8s infinite; }}
        .status-pill .dot.off {{ background: #6B7280; animation: none; }}

        /* ---- Overview / about panel ---- */
        .overview-card {{
            background: {CARD_BG}; border: 1px solid {CARD_BORDER};
            border-radius: 16px; padding: 1.6rem 1.8rem; margin-bottom: 1.6rem;
        }}
        .overview-card h2 {{ color: {TEXT_MAIN}; font-size: 1.25rem; font-weight: 800; margin: 0 0 0.5rem 0; }}
        .overview-card p {{ color: {TEXT_MUTED}; font-size: 0.92rem; line-height: 1.6; margin: 0 0 1.1rem 0; max-width: 720px; }}
        .pill-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
        .feature-pill {{
            background: rgba(47,128,237,0.1); border: 1px solid rgba(47,128,237,0.3);
            color: {TEXT_MAIN}; border-radius: 999px; padding: 0.3rem 0.85rem; font-size: 0.78rem; font-weight: 600;
        }}

        /* ---- Cards used throughout the app ---- */
        .glass-card {{
            background: {CARD_BG}; border: 1px solid {CARD_BORDER};
            border-radius: 16px; padding: 1.3rem 1.5rem; margin-bottom: 1rem; color: {TEXT_MAIN};
        }}
        .metric-pill {{
            background: {CARD_BG}; border: 1px solid {CARD_BORDER};
            border-radius: 14px; padding: 0.9rem 1.1rem; text-align: left;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        .metric-pill:hover {{ transform: translateY(-3px); border-color: {PRIMARY}; }}
        .metric-pill .label {{ color: {TEXT_MUTED}; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }}
        .metric-pill .value {{ color: {TEXT_MAIN}; font-size: 1.45rem; font-weight: 800; margin-top: 0.15rem; }}
        .metric-pill .value.accent {{ color: {ACCENT}; }}

        section[data-testid="stSidebar"] {{ background: #DCEEFF; border-right: 1px solid {CARD_BORDER}; }}
        section[data-testid="stSidebar"] .stButton button[kind="primary"] {{
            background: linear-gradient(135deg, {PRIMARY}, {PRIMARY_DARK});
            border: none; box-shadow: 0 6px 18px rgba(47,128,237,0.35);
        }}
        .stButton button {{ border-radius: 10px; font-weight: 700; }}

        .stTabs [data-baseweb="tab-list"] {{ gap: 6px; background: transparent; }}
        .stTabs [data-baseweb="tab"] {{
            background: {CARD_BG}; border: 1px solid {CARD_BORDER};
            border-radius: 10px 10px 0 0; padding: 0.55rem 1.1rem;
            color: {TEXT_MUTED}; font-weight: 600;
        }}
        .stTabs [aria-selected="true"] {{
            color: white !important;
            background: linear-gradient(135deg, {PRIMARY}, {PRIMARY_DARK}) !important;
            border-color: transparent !important;
        }}

        .chat-row {{ display: flex; margin-bottom: 0.7rem; animation: fadeInUp 0.3s ease-out both; }}
        .chat-row.user {{ justify-content: flex-end; }}
        .bubble {{ max-width: 75%; padding: 0.65rem 1rem; border-radius: 16px; font-size: 0.92rem; line-height: 1.45; }}
        .bubble.user {{ background: linear-gradient(135deg, {PRIMARY}, {PRIMARY_DARK}); color: white; border-bottom-right-radius: 4px; }}
        .bubble.assistant {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER}; color: {TEXT_MAIN}; border-bottom-left-radius: 4px; }}
        .typing-bubble {{
            display: inline-flex; gap: 4px; align-items: center;
            background: {CARD_BG}; border: 1px solid {CARD_BORDER};
            border-radius: 16px; border-bottom-left-radius: 4px; padding: 0.7rem 1rem;
        }}
        .typing-bubble span {{ width: 7px; height: 7px; border-radius: 50%; background: {TEXT_MUTED}; animation: bounce 1.2s infinite ease-in-out; }}
        .typing-bubble span:nth-child(2) {{ animation-delay: 0.15s; }}
        .typing-bubble span:nth-child(3) {{ animation-delay: 0.3s; }}

        div[data-testid="stStatusWidget"] {{ background: {CARD_BG} !important; border: 1px solid {CARD_BORDER} !important; border-radius: 14px !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "processing" not in st.session_state:
    st.session_state.processing = False
if "run_at" not in st.session_state:
    st.session_state.run_at = None


def run_pipeline(source: str, language: str) -> dict:
    status = st.status("🚀 Starting AI Video Assistant...", expanded=True)

    status.write("**Step 1/5** · Processing input...")
    chunks = process_input(source, language=language)

    status.write("**Step 2/5** · Transcribing audio...")
    transcript = transcribe_all(chunks, language=language)
    status.write(f"↳ Preview: _{transcript[:200].strip()}..._")

    llm_available = bool(os.getenv("MISTRAL_API_KEY"))

    if llm_available:
        def optional_llm_step(label: str, fallback: str, operation):
            try:
                return operation()
            except Exception as error:
                status.info(f"{label} switched to local transcript mode.")
                return fallback

        status.write("**Step 3/5** · Generating title & summary...")
        title = optional_llm_step(
            "Title generation",
            title_locally(transcript),
            lambda: generate_title(transcript),
        )
        summary = optional_llm_step(
            "Summary",
            summarize_locally(transcript),
            lambda: summarizer(transcript),
        )

        status.write("**Step 4/5** · Extracting insights...")
        action_item = optional_llm_step(
            "Action items",
            action_items_locally(transcript),
            lambda: extract_action_items(transcript),
        )
        decisions = optional_llm_step(
            "Key decisions",
            decisions_locally(transcript),
            lambda: extract_key_decisions(transcript),
        )
        questions = optional_llm_step(
            "Open questions",
            questions_locally(transcript),
            lambda: extract_questions(transcript),
        )

        status.write("**Step 5/5** · Building chat engine...")
        try:
            rag_chain = build_rag_chain(transcript)
        except Exception as error:
            status.warning(f"Chat engine unavailable: {error}")
            rag_chain = None
    else:
        title = "Meeting transcript captured"
        msg = "LLM unavailable: set MISTRAL_API_KEY in your .env file."
        summary = msg
        action_item = msg
        decisions = msg
        questions = msg
        rag_chain = None
        status.warning("MISTRAL_API_KEY not set — LLM features (summary, extraction, chat) are disabled.")

    status.update(label="✅ Pipeline complete", state="complete", expanded=False)

    return {
        "title": title,
        "transcript": transcript,
        "summary": summary,
        "action_items": action_item,
        "key_decisions": decisions,
        "open_questions": questions,
        "chat_fallback": transcript,
        "rag_chain": rag_chain,
    }


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def count_bullets(text: str) -> int:
    if not text:
        return 0
    lines = [l for l in text.splitlines() if l.strip()]
    bulletish = [l for l in lines if re.match(r"^\s*[-*•\d]", l.strip())]
    return len(bulletish) if bulletish else len(lines)


# ---------------------------------------------------------------------------
# Top bar
# ---------------------------------------------------------------------------
llm_on = bool(os.getenv("MISTRAL_API_KEY"))
dot_class = "dot" if llm_on else "dot off"
status_text = "LLM engine ready" if llm_on else "Basic mode — no LLM key"

st.markdown(
    f"""
    <div class="topbar-grid">
        <div class="left"></div>
        <div class="center">
            <div class="brand-float">
                <div class="brand-name">🤖 AI Video Assistant</div>
                <div class="brand-tag">Transcribe · Summarize · Chat</div>
            </div>
        </div>
        <div class="right">
            <span class="status-pill"><span class="{dot_class}"></span>{status_text}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Project overview panel
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="overview-card fade-in">
        <h2>Turn any meeting or video into a searchable, chat-ready record</h2>
        <p>Paste a YouTube link or upload a recording. The pipeline transcribes the audio, then generates
        a title, summary, action items, key decisions, and open questions — and builds a retrieval-augmented
        chat engine so you can ask follow-up questions grounded in the actual transcript.</p>
        <div class="pill-row">
            <span class="feature-pill">🎙️ YouTube & file transcription</span>
            <span class="feature-pill">🧠 AI summary & extraction</span>
            <span class="feature-pill">💬 RAG-powered chat</span>
            <span class="feature-pill">🌐 English & Hinglish</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar: input controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"""
        <div class="brand-float" style="margin-bottom:0.3rem;">
            <div style="color:#0F2A43;font-weight:800;font-size:1.1rem;line-height:1.2;">🤖 AI Video Assistant</div>
            <div style="color:#5B7A99;font-size:0.75rem;">Transcribe · Summarize · Chat</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<hr style='border-color:#CFE3FA;margin:0.8rem 0;'>", unsafe_allow_html=True)

    if not llm_on:
        st.warning("MISTRAL_API_KEY not set — LLM features disabled.", icon="⚠️")

    input_mode = st.radio("Source", ["YouTube URL", "Upload file"], horizontal=True)

    source = None
    if input_mode == "YouTube URL":
        source = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
    else:
        uploaded_file = st.file_uploader("Audio / video file", type=["mp4", "mp3", "wav", "m4a", "mov", "mkv"])
        if uploaded_file is not None:
            tmp_path = os.path.join(tempfile.gettempdir(), f"upload_{uploaded_file.name}")
            with open(tmp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            source = tmp_path
            st.caption(f"📁 `{uploaded_file.name}` ready")

    language = st.selectbox("Language", ["english", "hinglish"], index=0)

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    run_clicked = st.button(
        "▶  Run pipeline", type="primary", use_container_width=True,
        disabled=st.session_state.processing or not source,
    )

    if st.session_state.result is not None:
        if st.button("↺  Reset", use_container_width=True):
            st.session_state.result = None
            st.session_state.messages = []
            st.rerun()

    if st.session_state.run_at:
        st.markdown(f"<div style='color:#5B7A99;font-size:0.75rem;margin-top:1rem;'>Last run: {st.session_state.run_at}</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Run pipeline on click
# ---------------------------------------------------------------------------
if run_clicked and source:
    st.session_state.processing = True
    try:
        st.session_state.result = run_pipeline(source, language)
        st.session_state.messages = []
        st.session_state.run_at = datetime.now().strftime("%b %d, %H:%M")
    except Exception as e:
        st.error(f"Pipeline failed: {e}")
    finally:
        st.session_state.processing = False

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
result = st.session_state.result

if result is None:
    st.markdown(
        """
        <div class="glass-card fade-in" style="text-align:center;padding:3rem 1.5rem;">
            <div style="font-size:2.4rem;">📽️</div>
            <div style="color:#0F2A43;font-weight:700;font-size:1.15rem;margin-top:0.5rem;">Nothing processed yet</div>
            <div style="color:#5B7A99;margin-top:0.3rem;">Add a YouTube URL or upload a file in the sidebar, then hit <b>Run pipeline</b>.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    c1, c2, c3, c4 = st.columns(4)
    metrics = [
        ("Words transcribed", f"{word_count(result['transcript']):,}"),
        ("Action items", count_bullets(result["action_items"])),
        ("Key decisions", count_bullets(result["key_decisions"])),
        ("Open questions", count_bullets(result["open_questions"])),
    ]
    for i, (col, (label, value)) in enumerate(zip([c1, c2, c3, c4], metrics)):
        col.markdown(
            f"""
            <div class="metric-pill fade-in" style="animation-delay:{i * 0.08:.2f}s;">
                <div class="label">{label}</div>
                <div class="value accent">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:1.1rem'></div>", unsafe_allow_html=True)
    st.markdown(f"### {result['title']}")

    tab_summary, tab_actions, tab_decisions, tab_questions, tab_transcript, tab_chat = st.tabs(
        ["📝 Summary", "✅ Action Items", "📌 Decisions", "❓ Questions", "📄 Transcript", "💬 Chat"]
    )

    with tab_summary:
        st.markdown(f'<div class="glass-card">{result["summary"]}</div>', unsafe_allow_html=True)
    with tab_actions:
        st.markdown(f'<div class="glass-card">{result["action_items"]}</div>', unsafe_allow_html=True)
    with tab_decisions:
        st.markdown(f'<div class="glass-card">{result["key_decisions"]}</div>', unsafe_allow_html=True)
    with tab_questions:
        st.markdown(f'<div class="glass-card">{result["open_questions"]}</div>', unsafe_allow_html=True)

    with tab_transcript:
        st.text_area("Full transcript", result["transcript"], height=380, label_visibility="collapsed")
        st.download_button("⬇ Download transcript (.txt)", data=result["transcript"], file_name="transcript.txt", mime="text/plain")

    with tab_chat:
        rag_chain = result["rag_chain"]
        if rag_chain is None:
            st.info("Mistral is rate-limited, so chat is using transcript search mode.")
        else:
            chat_box = st.container()
            with chat_box:
                if not st.session_state.messages:
                    st.markdown(
                        "<div style='color:#5B7A99;text-align:center;padding:1.5rem;'>"
                        "💬 Ask anything about this meeting — e.g. \"What did we decide about the launch date?\""
                        "</div>",
                        unsafe_allow_html=True,
                    )
                for msg in st.session_state.messages:
                    role = msg["role"]
                    st.markdown(f'<div class="chat-row {role}"><div class="bubble {role}">{msg["content"]}</div></div>', unsafe_allow_html=True)

            question = st.chat_input("Ask something about the meeting...")
            if question:
                st.session_state.messages.append({"role": "user", "content": question})
                typing_placeholder = st.empty()
                typing_placeholder.markdown(
                    '<div class="chat-row assistant"><div class="typing-bubble"><span></span><span></span><span></span></div></div>',
                    unsafe_allow_html=True,
                )
                try:
                    answer = ask_question(rag_chain, question) if rag_chain else answer_locally(result["chat_fallback"], question)
                except Exception as error:
                    answer = answer_locally(result["chat_fallback"], question)
                    st.info("Mistral chat is rate-limited; using transcript search mode.")
                finally:
                    typing_placeholder.empty()
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.rerun()