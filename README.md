# AI Video Assistant

Turn any meeting or video into a searchable, chat-ready record. Paste a YouTube link or upload a recording. The pipeline transcribes the audio, then generates a title, summary, action items, key decisions, and open questions, and builds a retrieval-augmented chat engine for follow-up questions grounded in the transcript.

## Run locally

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

Create a local `.env` file in the repository root:

```text
MISTRAL_API_KEY=your_mistral_api_key
```

`.env` is ignored by Git. The app also supports the legacy `.venv/.env` location for existing local installations.

## Deploy with Streamlit Community Cloud

1. Push this repository and select the root `app.py` as the main file.
2. Open the app's **Settings > Secrets** in Streamlit Cloud.
3. Add the key in TOML format:

```toml
MISTRAL_API_KEY = "your_mistral_api_key"
# Optional, only for videos that return HTTP 403 or require sign-in:
# YOUTUBE_COOKIES = "# Netscape HTTP Cookie File\n..."
```

4. Save the secret and reboot the app.

The key must be configured in the deployment platform; it cannot be safely committed to the repository. Without it, transcription still works, but Mistral-powered summaries, extraction, and chat remain disabled.

The downloader uses yt-dlp's visionOS player client because YouTube's default client can return HTTP 403 or no usable formats in cloud environments. If a video is still blocked, export cookies in Netscape format from your browser and add the contents as the `YOUTUBE_COOKIES` Streamlit secret. Never commit cookie data to GitHub.
