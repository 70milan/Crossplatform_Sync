# Cross-Platform Sync: YouTube → Spotify

Standalone Python script that syncs your **YouTube Liked Music** into your **Spotify Liked Songs** library — no Dagster or orchestrator required.

This repository now includes both:
- a CLI runner (`cross_platform_sync.py`)
- a web UI shell (`ui_shell.py`) powered by Streamlit
- a React design preview (`frontend/`) for the upcoming web app

## How It Works

1. **Fetch State from S3** — Reads previously processed YouTube IDs from an AWS S3 state file.
2. **Pull YouTube Liked Music** — Authenticates via Google OAuth and fetches your Liked Music playlist.
3. **Extract Metadata** — Uses `yt_dlp` to pull track name & artist from each new video.
4. **Search Spotify** — Searches the Spotify catalog for each track/artist combo.
5. **Add to Spotify Likes** — Adds matched tracks to your Spotify Liked Songs (de-duplicated).
6. **Save State to S3** — Persists the updated list of processed YouTube IDs back to S3.

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Credentials

Edit `config.ini` and fill in your credentials:

- **`[aws_creds]`** — Your AWS access key and secret for the S3 bucket.
- **`[sp_creds]`** — Your Spotify Developer app's client ID, secret, and username.
- **`[google_api]`** — Your Google Cloud OAuth client credentials for YouTube Data API v3.

### 3. Run

```bash
python cross_platform_sync.py
```

On first run, browser windows will open for both **Google** and **Spotify** OAuth consent.

## UI Shell (End-to-End)

Run the web UI:

```bash
streamlit run ui_shell.py
```

Then:
1. Open the local Streamlit URL shown in terminal.
2. Click `Validate config` to verify required fields.
3. Click `Run full sync`.
4. Complete OAuth in browser windows if prompted.
5. Monitor live logs and summary metrics directly in the app.

### Optional Environment Overrides

You can override runtime values without changing code:

- `SYNC_S3_BUCKET` (default: `s3numerone`)
- `SYNC_S3_KEY` (default: `project_sp_yt/processed_yt_ids.csv`)
- `SP_REDIRECT_URI` (default: `http://localhost:7777/callback`)

## Project Structure

```
Crossplatform_Sync/
├── config.ini               # All API credentials (AWS, Spotify, Google)
├── cross_platform_sync.py   # Main sync script
├── ui_shell.py              # Streamlit UI shell for end-to-end runs
├── frontend/                # React UI design shell (browser app preview)
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## React UI Design Preview

To preview the upcoming web app UI in browser:

```bash
cd frontend
npm install
npm run dev
```

Then open the Vite URL shown in terminal (usually `http://localhost:5173`).

## Full App Run (Frontend + Backend)

Start the backend API in one terminal:

```bash
cd .
pip install -r requirements.txt
uvicorn backend_api:app --reload --host 127.0.0.1 --port 8000
```

Start the React frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open the frontend URL from Vite (usually `http://localhost:5173`).

The React app talks to the local API at `http://127.0.0.1:8000` by default.
