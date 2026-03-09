import traceback
from datetime import datetime

import streamlit as st

from cross_platform_sync import CONFIG_PATH, load_settings, run_pipeline, validate_settings

st.set_page_config(page_title="Cross-Platform Sync UI", page_icon=":musical_note:", layout="wide")

st.title("YouTube to Spotify Sync")
st.caption("UI shell for running the full cross-platform sync pipeline end to end.")

if "logs" not in st.session_state:
    st.session_state.logs = []
if "last_summary" not in st.session_state:
    st.session_state.last_summary = None

with st.sidebar:
    st.header("Run Settings")
    config_path = st.text_input("Config file path", value=CONFIG_PATH)
    st.markdown("S3 bucket and object key can be overridden with environment variables:")
    st.code("SYNC_S3_BUCKET\nSYNC_S3_KEY\nSP_REDIRECT_URI", language="bash")

col_a, col_b = st.columns(2)

with col_a:
    if st.button("Validate config", use_container_width=True):
        try:
            settings = load_settings(config_path)
            missing = validate_settings(settings)
            if missing:
                st.error(f"Missing values in config.ini: {', '.join(missing)}")
            else:
                st.success("Config looks valid.")
        except Exception as ex:
            st.error(f"Config validation failed: {ex}")

with col_b:
    if st.button("Clear log", use_container_width=True):
        st.session_state.logs = []
        st.session_state.last_summary = None
        st.rerun()

status_placeholder = st.empty()
metrics_placeholder = st.empty()
log_placeholder = st.empty()


def append_log(level: str, message: str, step: str | None = None, payload: dict | None = None):
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{timestamp}] {level.upper()}"
    if step:
        prefix += f" [{step}]"
    st.session_state.logs.append(f"{prefix} {message}")

    if payload:
        st.session_state.last_summary = payload

    if level == "error":
        status_placeholder.error(message)
    elif level == "warning":
        status_placeholder.warning(message)
    else:
        status_placeholder.info(message)

    log_placeholder.code("\n".join(st.session_state.logs[-200:]), language="text")


if st.button("Run full sync", type="primary", use_container_width=True):
    st.session_state.logs = []
    st.session_state.last_summary = None

    with st.spinner("Pipeline is running. OAuth browser windows may open for Google and Spotify."):
        try:
            summary = run_pipeline(config_path=config_path, emit=append_log)
            st.session_state.last_summary = summary
            status_placeholder.success("Sync completed successfully.")
        except Exception as ex:
            status_placeholder.error(f"Sync failed: {ex}")
            append_log("error", traceback.format_exc())

summary = st.session_state.last_summary
if summary:
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Extracted", summary.get("songs_extracted", 0))
    m2.metric("Matched", summary.get("songs_matched", 0))
    m3.metric("Added", summary.get("songs_added", 0))
    m4.metric("Problematic", summary.get("problematic_videos", 0))
    m5.metric("Elapsed (s)", summary.get("elapsed_seconds", 0))

    matched_tracks = summary.get("matched_track_names") or []
    if matched_tracks:
        st.subheader("Matched track names")
        st.write(matched_tracks)

if st.session_state.logs:
    log_placeholder.code("\n".join(st.session_state.logs[-200:]), language="text")
else:
    log_placeholder.info("Run the pipeline to view live logs here.")
