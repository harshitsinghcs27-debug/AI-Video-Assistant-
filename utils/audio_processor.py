import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

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
    cookie_data = os.getenv("YOUTUBE_COOKIES", "").strip()
    if cookie_data:
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

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if is_youtube_url(url):
                filename = os.path.splitext(filename)[0] + ".mp3"
            if not os.path.exists(filename):
                raise FileNotFoundError(f"Downloaded audio was not created: {filename}")
            return filename
    except yt_dlp.utils.DownloadError as exc:
        details = str(exc)
        if "Please sign in" in details or "private" in details.lower():
            raise RuntimeError(
                "YouTube could not provide this video without sign-in. "
                "Try a public video URL, update yt-dlp, or use a local file. "
                f"Details: {details}"
            ) from exc
        if "403" in details or "Forbidden" in details:
            raise RuntimeError(
                "YouTube rejected the audio request (HTTP 403). "
                "Update yt-dlp and, for restricted videos, add a Netscape-format "
                "YOUTUBE_COOKIES secret in Streamlit. Public videos may require "
                "a different video URL. "
                f"Details: {details}"
            ) from exc
        raise RuntimeError(f"Failed to download audio from YouTube: {details}") from exc
    finally:
        if cookie_file:
            try:
                os.unlink(cookie_file.name)
            except OSError:
                pass


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
        downloaded_path = download_audio(source)
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
