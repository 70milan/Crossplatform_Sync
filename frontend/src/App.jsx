import React, { useEffect, useState } from "react";
import SyncDirectionSection from "./components/SyncDirectionSection";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const STEP_DEFINITIONS = [
  { id: "step1", label: "1", title: "Load S3 State", detail: "Read processed YouTube IDs from S3" },
  { id: "step2", label: "2", title: "Fetch Liked Music", detail: "Authenticate with Google and extract metadata" },
  { id: "step3", label: "3", title: "Match on Spotify", detail: "Search Spotify and de-duplicate liked songs" },
  { id: "step4", label: "4", title: "Add New Tracks", detail: "Save new Spotify matches in batches" },
  { id: "step5", label: "5", title: "Persist State", detail: "Upload refreshed processed IDs to S3" },
];

function StepChip({ status }) {
  return <span className={`chip chip-${status}`}>{status}</span>;
}

function formatElapsed(summary, run) {
  if (summary?.elapsed_seconds !== undefined) {
    return `${summary.elapsed_seconds}s`;
  }
  if (!run?.started_at) {
    return "--";
  }
  const started = new Date(run.started_at).getTime();
  const finished = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  if (Number.isNaN(started) || Number.isNaN(finished)) {
    return "--";
  }
  return `${Math.max(0, Math.round((finished - started) / 1000))}s`;
}

function formatRunTime(value) {
  if (!value) {
    return "Pending";
  }
  return new Date(value).toLocaleString();
}

function buildSteps(run) {
  const activeIndex = STEP_DEFINITIONS.findIndex((step) => step.id === run?.active_step);
  const isCompleted = run?.status === "completed";
  const isFailed = run?.status === "failed";

  return STEP_DEFINITIONS.map((step, index) => {
    let status = "pending";
    if (isCompleted) {
      status = "done";
    } else if (isFailed && run?.active_step === step.id) {
      status = "failed";
    } else if (activeIndex >= 0 && index < activeIndex) {
      status = "done";
    } else if (run?.status === "running" && step.id === run?.active_step) {
      status = "active";
    }

    return {
      ...step,
      status,
    };
  });
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      // Ignore JSON parsing failures and fall back to the HTTP status.
    }
    throw new Error(message);
  }

  return response.json();
}

export default function App() {
  const [currentRun, setCurrentRun] = useState(null);
  const [history, setHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [banner, setBanner] = useState({ tone: "info", message: `Backend: ${API_BASE_URL}` });
  const [isStarting, setIsStarting] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [sourcePlatform, setSourcePlatform] = useState(null);
  const [selectionError, setSelectionError] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const loadStatus = async (quiet = false) => {
      try {
        const payload = await apiRequest("/api/sync/status");
        if (!isMounted) {
          return;
        }
        setCurrentRun(payload.current_run);
        setHistory(payload.history || []);
        if (!quiet) {
          setBanner({ tone: "info", message: `Connected to backend at ${API_BASE_URL}` });
        }
      } catch (error) {
        if (isMounted) {
          setBanner({ tone: "error", message: error.message });
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadStatus();
    const intervalId = window.setInterval(() => loadStatus(true), 2000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const handleValidate = async () => {
    if (!sourcePlatform) {
      setSelectionError(true);
      setBanner({ tone: "warning", message: "Choose a sync direction before validating credentials." });
      return;
    }

    setSelectionError(false);
    setIsValidating(true);
    try {
      const payload = await apiRequest("/api/config/validate", {
        method: "POST",
        body: JSON.stringify({ source_platform: sourcePlatform }),
      });
      if (payload.ok) {
        setBanner({ tone: "success", message: `Config valid: ${payload.config_path}` });
      } else {
        setBanner({ tone: "warning", message: `Missing config values: ${payload.missing.join(", ")}` });
      }
    } catch (error) {
      setBanner({ tone: "error", message: error.message });
    } finally {
      setIsValidating(false);
    }
  };

  const handleRun = async () => {
    if (!sourcePlatform) {
      setSelectionError(true);
      setBanner({ tone: "warning", message: "Choose a sync direction before starting the sync." });
      return;
    }

    setSelectionError(false);
    setIsStarting(true);
    try {
      const payload = await apiRequest("/api/sync/run", {
        method: "POST",
        body: JSON.stringify({ source_platform: sourcePlatform }),
      });
      setCurrentRun(payload);
      setBanner({ tone: "success", message: `Sync started for ${sourcePlatform} → ${sourcePlatform === "youtube" ? "spotify" : "youtube"}. OAuth browser windows may open.` });
    } catch (error) {
      setBanner({ tone: "error", message: error.message });
    } finally {
      setIsStarting(false);
    }
  };

  const handleDownloadLogs = () => {
    const lines = currentRun?.logs || [];
    if (!lines.length) {
      setBanner({ tone: "warning", message: "No logs available to download yet." });
      return;
    }

    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `sync-run-${currentRun.run_id || "latest"}.log`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const summary = currentRun?.summary || {};
  const steps = buildSteps(currentRun);
  const logs = currentRun?.logs || [];
  const runStatus = currentRun?.status || "idle";
  const handleDirectionSelect = (platformKey) => {
    setSourcePlatform(platformKey);
    setSelectionError(false);
  };

  return (
    <div className="app-shell">
      <div className="stars" aria-hidden="true" />
      <div className="moon" aria-hidden="true" />
      <div className="cloud cloud-1" aria-hidden="true" />
      <div className="cloud cloud-2" aria-hidden="true" />
      <div className="cloud cloud-3" aria-hidden="true" />

      <SyncDirectionSection
        sourcePlatform={sourcePlatform}
        onSelect={handleDirectionSelect}
        onRun={handleRun}
        onValidate={handleValidate}
        isStarting={isStarting}
        isValidating={isValidating}
        runStatus={runStatus}
        selectionError={selectionError}
      />

      <section className={`status-banner tone-${banner.tone}`}>
        <strong>Status:</strong> {banner.message}
      </section>

      <div className="metrics-row">
        <div className="metric-block">
          <span className="value">{summary.songs_extracted ?? "--"}</span>
          <span className="label">Extracted</span>
        </div>
        <div className="metric-block">
          <span className="value">{summary.songs_matched ?? "--"}</span>
          <span className="label">Matched</span>
        </div>
        <div className="metric-block">
          <span className="value">{summary.songs_added ?? "--"}</span>
          <span className="label">Added</span>
        </div>
        <div className="metric-block">
          <span className="value">{formatElapsed(summary, currentRun)}</span>
          <span className="label">Elapsed</span>
        </div>
      </div>

      <div className="layout-grid">
        <section className="panel">
          <div className="panel-title-row">
            <h2>Pipeline</h2>
            <span className="live-dot">{runStatus}</span>
          </div>
          <ol>
            {steps.map((step) => (
              <li key={step.id} className="step-row">
                <div className="step-index">{step.label}</div>
                <div className="step-copy">
                  <h3>{step.title}</h3>
                  <p>{step.detail}</p>
                </div>
                <StepChip status={step.status} />
              </li>
            ))}
          </ol>
        </section>

        <section className="panel">
          <h2>Recent Runs</h2>
          <div className="history-list">
            {history.length ? (
              history.map((run) => {
                const runSummary = run.summary || {};
                return (
                  <article key={run.run_id} className="history-card">
                    <h3>{formatRunTime(run.started_at)}</h3>
                    <p>{run.status.toUpperCase()}</p>
                    <p>
                      +{runSummary.songs_added ?? 0} added · {runSummary.songs_extracted ?? 0} extracted · {runSummary.problematic_videos ?? 0} problematic
                    </p>
                    <p>{runSummary.elapsed_seconds ?? "--"}s</p>
                  </article>
                );
              })
            ) : (
              <article className="history-card history-empty">
                <h3>No runs yet</h3>
                <p>Start your first sync from the button above.</p>
              </article>
            )}
          </div>
        </section>

        <section className="panel panel-full">
          <div className="panel-title-row">
            <h2>Live Logs</h2>
            <button className="btn-text" onClick={handleDownloadLogs}>↓ Download</button>
          </div>
          <div className="log-window">
            {isLoading ? (
              <p>Loading backend status...</p>
            ) : logs.length ? (
              logs.map((line, index) => <p key={`${index}-${line}`}>{line}</p>)
            ) : (
              <p>Start a sync run to see logs here.</p>
            )}
          </div>
          {currentRun?.error ? <p className="error-copy">Last error: {currentRun.error}</p> : null}
        </section>
      </div>
    </div>
  );
}
