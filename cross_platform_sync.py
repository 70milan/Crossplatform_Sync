"""Cross-Platform Sync core pipeline and CLI entrypoint."""

import logging
import os
import time
from configparser import ConfigParser
from typing import Any, Callable
from urllib.parse import quote_plus

import boto3
import google_auth_oauthlib.flow
import googleapiclient.discovery
import requests
import yt_dlp
from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("CrossPlatformSync")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

EventCallback = Callable[[str, str, str | None, dict[str, Any] | None], None]


def _emit(
    callback: EventCallback | None,
    level: str,
    message: str,
    step: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if callback:
        callback(level, message, step, payload)
        return

    if level == "error":
        log.error(message)
    elif level == "warning":
        log.warning(message)
    else:
        log.info(message)


def load_settings(config_path: str = CONFIG_PATH) -> dict[str, str]:
    config = ConfigParser()
    if not config.read(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    return {
        "aws_access_key_id": config.get("aws_creds", "aws_access_key_id"),
        "aws_secret_access_key": config.get("aws_creds", "aws_secret_access_key"),
        "s3_bucket": os.getenv("SYNC_S3_BUCKET", "s3numerone"),
        "s3_key": os.getenv("SYNC_S3_KEY", "project_sp_yt/processed_yt_ids.csv"),
        "sp_client_id": config.get("sp_creds", "client_id"),
        "sp_client_secret": config.get("sp_creds", "client_secret"),
        "sp_redirect_uri": os.getenv("SP_REDIRECT_URI", "http://localhost:7777/callback"),
        "google_client_id": config.get("google_api", "client_id"),
        "google_project_id": config.get("google_api", "project_id"),
        "google_auth_uri": config.get("google_api", "auth_uri"),
        "google_token_uri": config.get("google_api", "token_uri"),
        "google_cert_url": config.get("google_api", "auth_provider_x509_cert_url"),
        "google_client_secret": config.get("google_api", "client_secret"),
        "google_redirect_uri": config.get("google_api", "redirect_uris"),
    }


def validate_settings(settings: dict[str, str]) -> list[str]:
    required_fields = [
        "aws_access_key_id",
        "aws_secret_access_key",
        "sp_client_id",
        "sp_client_secret",
        "google_client_id",
        "google_project_id",
        "google_auth_uri",
        "google_token_uri",
        "google_cert_url",
        "google_client_secret",
        "google_redirect_uri",
    ]
    return [key for key in required_fields if not settings.get(key, "").strip()]


def fetch_processed_yt_ids(settings: dict[str, str], emit: EventCallback | None = None) -> list[str]:
    _emit(emit, "info", "Step 1/5: Loading processed YouTube IDs from S3", "step1")
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings["aws_access_key_id"],
        aws_secret_access_key=settings["aws_secret_access_key"],
    )

    try:
        s3.head_object(Bucket=settings["s3_bucket"], Key=settings["s3_key"])
    except Exception:
        _emit(emit, "warning", "State file missing in S3. Creating an empty file.", "step1")
        s3.put_object(Body="", Bucket=settings["s3_bucket"], Key=settings["s3_key"])

    obj = s3.get_object(Bucket=settings["s3_bucket"], Key=settings["s3_key"])
    processed_ids = obj["Body"].read().decode().splitlines()
    _emit(emit, "info", f"Loaded {len(processed_ids)} processed IDs.", "step1")
    return processed_ids


def fetch_youtube_music(
    settings: dict[str, str],
    processed_yt_ids: list[str],
    emit: EventCallback | None = None,
) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    _emit(emit, "info", "Step 2/5: Pulling YouTube liked music and extracting metadata", "step2")

    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    client_config = {
        "installed": {
            "client_id": settings["google_client_id"],
            "project_id": settings["google_project_id"],
            "auth_uri": settings["google_auth_uri"],
            "token_uri": settings["google_token_uri"],
            "auth_provider_x509_cert_url": settings["google_cert_url"],
            "client_secret": settings["google_client_secret"],
            "redirect_uris": [settings["google_redirect_uri"]],
        }
    }
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(client_config, scopes)
    credentials = flow.run_local_server(port=8080)
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    yt_videos: list[tuple[str, str]] = []
    request = youtube.playlistItems().list(
        part="snippet,contentDetails", playlistId="LM", maxResults=50
    )
    response = request.execute()
    total_results = response.get("pageInfo", {}).get("totalResults", 0)
    _emit(emit, "info", f"Liked music playlist contains {total_results} videos.", "step2")

    while response:
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            video_id = snippet.get("resourceId", {}).get("videoId")
            video_title = snippet.get("title", "")
            if video_id:
                yt_videos.append((video_id, video_title))

        next_page = response.get("nextPageToken")
        if not next_page:
            break
        request = youtube.playlistItems().list(
            part="snippet", playlistId="LM", maxResults=50, pageToken=next_page
        )
        response = request.execute()

    processed_ids_only = {line.split(",")[0] for line in processed_yt_ids if line}
    new_videos = [video for video in yt_videos if video[0] not in processed_ids_only]
    _emit(emit, "info", f"Found {len(new_videos)} unprocessed videos.", "step2")

    yt_songs: list[tuple[str, str]] = []
    problematic_videos: list[str] = []
    ydl_opts = {"quiet": True, "no_warnings": True}

    for idx, (video_id, _) in enumerate(new_videos, start=1):
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            track = info.get("title", "Unknown Track")
            artist = info.get("uploader", "Unknown Artist").replace(" - Topic", "")
            yt_songs.append((track, artist))
            _emit(emit, "info", f"[{idx}/{len(new_videos)}] Extracted {track} - {artist}", "step2")
        except (yt_dlp.utils.ExtractorError, yt_dlp.utils.DownloadError):
            problematic_videos.append(video_id)
            _emit(emit, "warning", f"[{idx}/{len(new_videos)}] Failed extraction for {video_url}", "step2")

    for video_id, video_title in new_videos:
        processed_yt_ids.append(f"{video_id},{video_title}")

    _emit(
        emit,
        "info",
        f"Metadata extracted for {len(yt_songs)} songs. Problematic videos: {len(problematic_videos)}.",
        "step2",
    )
    return yt_songs, problematic_videos, processed_yt_ids


def search_spotify_for_tracks(
    settings: dict[str, str],
    yt_songs: list[tuple[str, str]],
    emit: EventCallback | None = None,
) -> tuple[list[str], list[str]]:
    _emit(emit, "info", "Step 3/5: Searching Spotify for candidate tracks", "step3")

    auth_manager = SpotifyOAuth(
        client_id=settings["sp_client_id"],
        client_secret=settings["sp_client_secret"],
        redirect_uri=settings["sp_redirect_uri"],
        scope="user-library-read",
    )
    access_token = auth_manager.get_access_token(as_dict=False)
    headers = {"Authorization": f"Bearer {access_token}"}

    first_page = requests.get(
        "https://api.spotify.com/v1/me/tracks?limit=50",
        headers=headers,
        timeout=30,
    ).json()
    if "error" in first_page:
        msg = first_page["error"].get("message", "Unknown Spotify error")
        raise RuntimeError(f"Spotify API error while reading liked songs: {msg}")

    total = first_page.get("total", 0)
    all_items = first_page.get("items", [])
    _emit(emit, "info", f"Spotify currently has {total} liked songs.", "step3")

    for offset in range(50, total, 50):
        page = requests.get(
            f"https://api.spotify.com/v1/me/tracks?offset={offset}&limit=50",
            headers=headers,
            timeout=30,
        ).json()
        all_items.extend(page.get("items", []))

    existing_uris = {
        item.get("track", {}).get("uri") for item in all_items if item.get("track", {}).get("uri")
    }

    spotify_uris: list[str] = []
    spotify_names: list[str] = []
    not_found = 0
    for idx, (track, artist) in enumerate(yt_songs, start=1):
        query = quote_plus(f"track:{track} artist:{artist}")
        search_url = f"https://api.spotify.com/v1/search?q={query}&type=track&limit=1"
        results = requests.get(search_url, headers=headers, timeout=30).json()
        items = results.get("tracks", {}).get("items", [])

        if not items:
            not_found += 1
            _emit(emit, "warning", f"[{idx}/{len(yt_songs)}] Not found: {track} - {artist}", "step3")
            continue

        uri = items[0]["uri"]
        name = items[0]["name"]
        spotify_uris.append(uri)
        spotify_names.append(name)
        _emit(emit, "info", f"[{idx}/{len(yt_songs)}] Matched: {name}", "step3")

    new_uris = [uri for uri in spotify_uris if uri not in existing_uris]
    new_names = [name for uri, name in zip(spotify_uris, spotify_names) if uri not in existing_uris]
    _emit(emit, "info", f"Spotify matches not found: {not_found}. New unique matches: {len(new_uris)}.", "step3")
    return new_uris, new_names


def add_tracks_to_spotify(
    settings: dict[str, str],
    new_uris: list[str],
    emit: EventCallback | None = None,
) -> int:
    _emit(emit, "info", "Step 4/5: Adding new songs to Spotify liked songs", "step4")
    if not new_uris:
        _emit(emit, "info", "No new songs to add.", "step4")
        return 0

    auth_manager = SpotifyOAuth(
        client_id=settings["sp_client_id"],
        client_secret=settings["sp_client_secret"],
        redirect_uri=settings["sp_redirect_uri"],
        scope="user-library-modify",
    )
    access_token = auth_manager.get_access_token(as_dict=False)
    spotify = Spotify(auth=access_token)

    total_added = 0
    for index in range(0, len(new_uris), 50):
        batch = new_uris[index : index + 50]
        try:
            spotify.current_user_saved_tracks_add(tracks=batch)
            total_added += len(batch)
            _emit(emit, "info", f"Added batch {index // 50 + 1} with {len(batch)} tracks.", "step4")
        except SpotifyException as ex:
            _emit(emit, "error", f"Failed to add batch {index // 50 + 1}: {ex}", "step4")

    _emit(emit, "info", f"Total songs added to Spotify: {total_added}", "step4")
    return total_added


def upload_processed_yt_ids(
    settings: dict[str, str],
    processed_yt_ids: list[str],
    total_added: int,
    emit: EventCallback | None = None,
) -> None:
    _emit(emit, "info", "Step 5/5: Uploading updated processed IDs to S3", "step5")
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings["aws_access_key_id"],
        aws_secret_access_key=settings["aws_secret_access_key"],
    )
    body = "\n".join(processed_yt_ids)
    s3.put_object(Body=body, Bucket=settings["s3_bucket"], Key=settings["s3_key"])
    _emit(
        emit,
        "info",
        f"Saved {len(processed_yt_ids)} IDs to s3://{settings['s3_bucket']}/{settings['s3_key']} (added {total_added}).",
        "step5",
    )


def run_pipeline(config_path: str = CONFIG_PATH, emit: EventCallback | None = None) -> dict[str, Any]:
    start = time.time()
    _emit(emit, "info", "Starting YouTube to Spotify sync", "init")

    settings = load_settings(config_path)
    missing = validate_settings(settings)
    if missing:
        raise ValueError(f"Missing config values: {', '.join(missing)}")

    processed_ids = fetch_processed_yt_ids(settings, emit)
    yt_songs, problematic, processed_ids_updated = fetch_youtube_music(settings, processed_ids, emit)
    new_uris, new_names = search_spotify_for_tracks(settings, yt_songs, emit)
    total_added = add_tracks_to_spotify(settings, new_uris, emit)
    upload_processed_yt_ids(settings, processed_ids_updated, total_added, emit)

    elapsed = round(time.time() - start, 1)
    summary = {
        "elapsed_seconds": elapsed,
        "songs_extracted": len(yt_songs),
        "songs_matched": len(new_uris),
        "songs_added": total_added,
        "problematic_videos": len(problematic),
        "matched_track_names": new_names,
    }
    _emit(emit, "info", f"Pipeline finished in {elapsed}s", "done", summary)
    return summary


def main() -> None:
    try:
        summary = run_pipeline()
    except Exception as ex:
        log.exception("Pipeline failed: %s", ex)
        raise

    log.info("=" * 60)
    log.info("Pipeline complete")
    log.info("Songs extracted from YouTube : %s", summary["songs_extracted"])
    log.info("Songs matched on Spotify     : %s", summary["songs_matched"])
    log.info("Songs added to Spotify       : %s", summary["songs_added"])
    log.info("Problematic videos skipped   : %s", summary["problematic_videos"])
    log.info("Total elapsed time (seconds) : %s", summary["elapsed_seconds"])
    log.info("=" * 60)


if __name__ == "__main__":
    main()
