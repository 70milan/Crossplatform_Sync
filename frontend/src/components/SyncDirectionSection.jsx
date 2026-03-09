import React from "react";

const PLATFORMS = {
  youtube: {
    key: "youtube",
    label: "YouTube",
    logoClass: "brand-logo-youtube",
    logoSrc: "/youtube-pixel.png",
  },
  spotify: {
    key: "spotify",
    label: "Spotify",
    logoClass: "brand-logo-spotify",
    logoSrc: "/spotify-pixel.png",
  },
};

export default function SyncDirectionSection({
  sourcePlatform,
  onSelect,
  onRun,
  onValidate,
  isStarting,
  isValidating,
  runStatus,
  selectionError,
}) {
  const hasSelection = Boolean(sourcePlatform);
  const primaryPlatform = hasSelection ? PLATFORMS[sourcePlatform] : PLATFORMS.youtube;
  const secondaryPlatform = hasSelection
    ? PLATFORMS[sourcePlatform === "youtube" ? "spotify" : "youtube"]
    : PLATFORMS.spotify;

  return (
    <header className="hero hero-module">
      <p className="kicker">Personal Sync Console</p>
      <div className={`brand-strip ${hasSelection ? "is-selected" : "is-unselected"}`} aria-label="Platform direction selector">
        <button
          className={`brand-button ${sourcePlatform === primaryPlatform.key ? "is-active" : ""}`}
          type="button"
          onClick={() => onSelect(primaryPlatform.key)}
          aria-label={`Set ${primaryPlatform.label} as source platform`}
        >
          <img className={`brand-logo ${primaryPlatform.logoClass}`} src={primaryPlatform.logoSrc} alt={primaryPlatform.label} />
        </button>
        <span className="brand-arrow" aria-hidden="true">→</span>
        <button
          className={`brand-button ${sourcePlatform === secondaryPlatform.key ? "is-active" : ""}`}
          type="button"
          onClick={() => onSelect(secondaryPlatform.key)}
          aria-label={`Set ${secondaryPlatform.label} as source platform`}
        >
          <img className={`brand-logo ${secondaryPlatform.logoClass}`} src={secondaryPlatform.logoSrc} alt={secondaryPlatform.label} />
        </button>
      </div>
      <div className="title-stack" aria-label="Platform direction text">
        <button
          className={`title-platform title-platform-primary ${sourcePlatform === primaryPlatform.key ? "is-active" : ""}`}
          type="button"
          onClick={() => onSelect(primaryPlatform.key)}
        >
          {primaryPlatform.label}
        </button>
        <div className="title-platform-row">
          <span className="title-arrow" aria-hidden="true">→</span>
          <button
            className={`title-platform title-platform-secondary ${sourcePlatform === secondaryPlatform.key ? "is-active" : ""}`}
            type="button"
            onClick={() => onSelect(secondaryPlatform.key)}
          >
            {secondaryPlatform.label}
          </button>
        </div>
      </div>
      <p className="subhead">
        Trigger the real Python sync pipeline, follow each stage, and keep a live history of runs in your browser.
      </p>
      {selectionError ? <div className="pixel-error">8-BIT ERROR: SELECT YT → SP OR SP → YT TO START.</div> : null}
      <div className="hero-actions">
        <button className="btn btn-primary" onClick={onRun} disabled={isStarting || runStatus === "running"}>
          {runStatus === "running" ? "Running..." : isStarting ? "Starting..." : "Run Sync"}
        </button>
        <button className="btn btn-ghost" onClick={onValidate} disabled={isValidating || runStatus === "running"}>
          {isValidating ? "Checking..." : "Validate Creds"}
        </button>
      </div>
    </header>
  );
}
