import os
import re
import base64
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

from youtube_transcript_api import YouTubeTranscriptApi
from deep_translator import GoogleTranslator

try:
    import yt_dlp
except ModuleNotFoundError as exc:
    raise SystemExit(
        "yt_dlp is not installed in the active Python environment. "
        "Use the project venv: .\\.venv\\Scripts\\python.exe -m pip install -r .\\.venv\\Requirements.txt"
    ) from exc

try:
    import audioop
except ModuleNotFoundError:
    raise RuntimeError(
        "Audio processing requires Python 3.12 or the audioop-lts package."
    )

sys.modules.setdefault("pyaudioop", audioop)
from pydub import AudioSegment

DOWNLOAD_DIR = Path(__file__).resolve().parents[1] / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG_PATH = os.environ.get("FFMPEG_PATH")
if FFMPEG_PATH and Path(FFMPEG_PATH).exists():
    os.environ["PATH"] = FFMPEG_PATH + os.pathsep + os.environ.get("PATH", "")

if not shutil.which("ffmpeg"):
    raise RuntimeError(
        "FFmpeg is required for audio processing. Install it or set FFMPEG_PATH "
        "to the directory containing the ffmpeg executable."
    )


def download_audio(url: str) -> str:
    url = normalize_youtube_url(url)
    output_template = str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["visionos"],
            },
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        },
    }
    cookie_file = None
    cookie_data = get_youtube_cookie_data()
    if cookie_data and is_netscape_cookie_data(cookie_data):
        cookie_file = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        )
        cookie_file.write(cookie_data)
        cookie_file.close()
        ydl_opts["cookiefile"] = cookie_file.name

    if is_youtube_url(url):
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    invalid_cookie_message = (
        " Ignoring YOUTUBE_COOKIES because it is not Netscape format; "
        "remove that secret for public videos or replace it with an exported "
        "Netscape cookie file."
        if cookie_data and not is_netscape_cookie_data(cookie_data)
        else ""
    )

    def cleanup_cookie_file() -> None:
        if cookie_file:
            try:
                os.unlink(cookie_file.name)
            except OSError:
                pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if is_youtube_url(url):
                filename = os.path.splitext(filename)[0] + ".mp3"
            if not os.path.exists(filename):
                raise FileNotFoundError(f"Downloaded audio was not created: {filename}")
            cleanup_cookie_file()
            return filename
    except yt_dlp.utils.DownloadError as exc:
        details = str(exc)
        if "Please sign in" in details or "private" in details.lower() or "not a bot" in details:
            cleanup_cookie_file()
            raise RuntimeError(
                "YouTube could not provide this video without sign-in. "
                "Add fresh Netscape cookies using YOUTUBE_COOKIES_B64, or use a "
                "public video URL/local file. "
                f"Details: {details}"
            ) from exc
        if "403" in details or "Forbidden" in details:
            cleanup_cookie_file()
            raise RuntimeError(
                "YouTube rejected the audio request (HTTP 403). "
                "Update yt-dlp and, for restricted videos, add a Netscape-format "
                "YOUTUBE_COOKIES secret in Streamlit. Public videos may require "
                "a different video URL. "
                f"Details: {details}{invalid_cookie_message}"
            ) from exc
        cleanup_cookie_file()
        raise RuntimeError(
            f"Failed to download audio from YouTube: {details}{invalid_cookie_message}"
        ) from exc


def is_netscape_cookie_data(cookie_data: str) -> bool:
    """Check that cookie text is suitable for yt-dlp's cookiefile option."""
    lines = [line.strip() for line in cookie_data.splitlines() if line.strip()]
    if not lines:
        return False
    if lines[0].startswith("-----BEGIN") or lines[0].startswith("{"):
        return False
    data_lines = [line for line in lines if not line.startswith("#")]
    return bool(data_lines) and all(len(line.split("\t")) == 7 for line in data_lines)


def get_youtube_cookie_data() -> str:
    """Read cookies from raw or base64 secrets without accepting JSON exports."""
    encoded = os.getenv("YOUTUBE_COOKIES_B64", "").strip()
    if encoded:
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            if is_netscape_cookie_data(decoded):
                return decoded.strip()
        except (ValueError, UnicodeDecodeError):
            pass

    raw = os.getenv("YOUTUBE_COOKIES", "").strip()
    if "\\n" in raw and "\n" not in raw:
        raw = raw.replace("\\n", "\n")
    return raw


def is_youtube_url(source: str) -> bool:
    """Return whether a source uses a supported YouTube host."""
    try:
        hostname = (urlparse(source).hostname or "").lower()
    except ValueError:
        return False
    return hostname in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}


def normalize_youtube_url(source: str) -> str:
    """Normalize watch, short, Shorts, and embed URLs for yt-dlp."""
    source = source.strip()
    if not is_youtube_url(source):
        return source

    parsed = urlparse(source)
    hostname = (parsed.hostname or "").lower()
    video_id = ""

    if hostname in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    else:
        match = re.match(r"^/(?:shorts/|embed/|live/)([^/?]+)", parsed.path)
        if match:
            video_id = match.group(1)

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return urlunparse(parsed._replace(fragment=""))


def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to WAV format using pydub."""
    output_path = os.path.splitext(input_path)[0] + "_converted.wav"
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000)
    audio.export(output_path, format="wav")
    return output_path


def chunk_audio(wav_path: str, chunk_minutes: int = 10) -> list[str]:
    """Split a WAV file into fixed-size chunks and return the paths."""
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000

    if len(audio) <= chunk_ms:
        return [wav_path]

    base_path = os.path.splitext(wav_path)[0]
    chunk_paths = []
    for index, start in enumerate(range(0, len(audio), chunk_ms), start=1):
        end = min(start + chunk_ms, len(audio))
        chunk = audio[start:end]
        chunk_path = f"{base_path}_chunk_{index}.wav"
        chunk.export(chunk_path, format="wav")
        chunk_paths.append(chunk_path)

    return chunk_paths


def process_input(source: str) -> list:
    """Process the input source (URL or local file) and return a list of WAV file paths."""
    source = source.strip()
    if source.startswith("http://") or source.startswith("https://"):
        print("Detected remote audio URL. Downloading...")
        try:
            downloaded_path = download_audio(source)
        except RuntimeError as download_error:
            if not is_youtube_url(source):
                raise
            print(f"YouTube audio unavailable; trying captions: {download_error}")
            transcript_path = download_youtube_transcript(source)
            return [transcript_path]
        if not os.path.exists(downloaded_path):
            raise FileNotFoundError(f"Audio download failed: {downloaded_path}")
        if os.path.splitext(downloaded_path)[1].lower() == ".wav":
            wav_path = downloaded_path
        else:
            wav_path = convert_to_wav(downloaded_path)
    else:
        if not os.path.exists(source):
            raise FileNotFoundError(f"Input file does not exist: {source}")
        print("Detected local file. CONVERTING TO WAV....")
        wav_path = convert_to_wav(source) if os.path.splitext(source)[1].lower() != ".wav" else source

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    print(f"Audio ready - {len(chunks)} chunk(s) created.")
    return chunks


def download_youtube_transcript(url: str) -> str:
    """Save YouTube captions locally when media download is blocked by YouTube."""
    normalized_url = normalize_youtube_url(url)
    parsed = urlparse(normalized_url)
    video_id = parse_qs(parsed.query).get("v", [""])[0]
    if not video_id:
        raise RuntimeError(
            "YouTube blocked the audio download and this URL has no video ID. "
            "Try a standard youtube.com/watch URL or upload the video file."
        )

    try:
        transcript_api = YouTubeTranscriptApi()
        transcript = transcript_api.fetch(
            video_id, languages=["en", "en-US", "hi"]
        )
        text = " ".join(snippet.text.strip() for snippet in transcript).strip()
        if getattr(transcript, "language_code", "") == "hi":
            text = translate_hindi_to_english(text)
    except Exception as transcript_error:
        text = download_youtube_subtitles_with_ytdlp(url)
        if not text:
            raise RuntimeError(
                "YouTube blocked audio and no accessible captions were found. "
                "Upload the media file. "
                f"Caption details: {transcript_error}"
            ) from transcript_error

    if not text:
        raise RuntimeError(
            "YouTube blocked audio and the video's captions were empty. "
            "Upload the media file instead."
        )

    transcript_path = DOWNLOAD_DIR / f"{video_id}_youtube_transcript.txt"
    transcript_path.write_text(text, encoding="utf-8")
    return str(transcript_path)


def download_youtube_subtitles_with_ytdlp(url: str) -> str:
    """Use yt-dlp subtitle endpoints as a second caption route."""
    subtitle_template = str(DOWNLOAD_DIR / "%(id)s.%(language)s.vtt")
    options = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "hi"],
        "subtitlesformat": "vtt",
        "outtmpl": subtitle_template,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["visionos"]}},
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError:
        return ""

    subtitle_files = sorted(DOWNLOAD_DIR.glob(f"{video_id_from_url(url)}.*.vtt"))
    if not subtitle_files:
        return ""
    subtitle_file = next(
        (path for path in subtitle_files if ".hi." in path.name), subtitle_files[0]
    )
    is_hindi = ".hi." in subtitle_file.name
    subtitle_text = subtitle_file.read_text(encoding="utf-8")
    for subtitle_file in subtitle_files:
        subtitle_file.unlink(missing_ok=True)
    lines = []
    for line in subtitle_text.splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        if not lines or lines[-1] != line:
            lines.append(line)
    text = " ".join(lines).strip()
    return translate_hindi_to_english(text) if is_hindi else text


def translate_hindi_to_english(text: str) -> str:
    """Translate Hindi caption text to English in service-sized chunks."""
    if not text.strip():
        return text

    try:
        translator = GoogleTranslator(source="hi", target="en")
        chunks = [text[index:index + 3500] for index in range(0, len(text), 3500)]
        translated = [translator.translate(chunk) for chunk in chunks]
        return " ".join(part.strip() for part in translated if part and part.strip())
    except Exception as error:
        print(f"Hindi caption translation unavailable; using original text: {error}")
        return text


def video_id_from_url(url: str) -> str:
    parsed = urlparse(normalize_youtube_url(url))
    return parse_qs(parsed.query).get("v", [""])[0]
