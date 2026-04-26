"use client";

import { useState } from "react";

const defaultWeek = new Date().toISOString().slice(0, 10);
const operatorProductKey = "indmoney";

function icon(name) {
  return <span className="material-symbols-outlined">{name}</span>;
}

export function TriggerPanel({ apiBaseUrl, scheduler }) {
  const [isoWeek, setIsoWeek] = useState("");
  const [draftOnly, setDraftOnly] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [status, setStatus] = useState("");
  const [busyAction, setBusyAction] = useState("");

  async function triggerSingleRun() {
    setBusyAction("run");
    setStatus("Submitting INDMoney one-shot flow...");
    try {
      const response = await fetch(`${apiBaseUrl}/api/trigger/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          product_key: operatorProductKey,
          iso_week: isoWeek || null,
          draft_only: draftOnly,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Request failed");
      }
      setStatus(
        `Queued INDMoney flow ${payload.job.job_id} in ${draftOnly ? "draft-only" : "send-enabled"} mode. Watch Background Jobs and Delivery Audit for progress.`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unknown request failure");
    } finally {
      setBusyAction("");
    }
  }

  async function toggleScheduler() {
    const nextEnabled = !scheduler?.enabled;
    setBusyAction("scheduler");
    setStatus(
      nextEnabled
        ? "Enabling periodic INDMoney scheduler..."
        : "Disabling periodic INDMoney scheduler...",
    );
    try {
      const response = await fetch(`${apiBaseUrl}/api/scheduler`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Scheduler update failed");
      }
      setStatus(
        nextEnabled
          ? `Periodic INDMoney scheduler enabled. Next run: ${payload.next_run_local || "scheduled from backend cadence"}.`
          : "Periodic INDMoney scheduler disabled. One-shot runs remain available.",
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unknown scheduler failure");
    } finally {
      setBusyAction("");
    }
  }

  async function uploadCsvAndRun() {
    if (!csvFile) {
      setStatus("Choose a CSV file before uploading.");
      return;
    }
    setBusyAction("csv");
    setStatus(`Uploading ${csvFile.name} and queuing CSV-driven INDMoney flow...`);
    try {
      const csvText = await csvFile.text();
      const query = new URLSearchParams({
        product_key: operatorProductKey,
        draft_only: String(draftOnly),
      });
      if (isoWeek) {
        query.set("iso_week", isoWeek);
      }
      const response = await fetch(`${apiBaseUrl}/api/trigger/upload-csv?${query.toString()}`, {
        method: "POST",
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
        },
        body: csvText,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "CSV upload failed");
      }
      setStatus(
        `Queued CSV flow ${payload.job.job_id} with ${payload.job.uploaded_rows || "uploaded"} row(s) in ${draftOnly ? "draft-only" : "send-enabled"} mode.`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unknown CSV upload failure");
    } finally {
      setBusyAction("");
    }
  }

  return (
    <section className="control-panel" id="scheduler">
      <div className="panel-chrome" aria-hidden="true" />
      <div className="control-heading">
        <div>
          <p className="eyebrow">Flow Control</p>
          <h2>
            {icon("route")}
            Run one flow now or control the periodic scheduler
          </h2>
          <p className="muted">
            INDMoney only. One-shot runs send to the configured recipient by default; switch to
            draft-only when you want a safe preview.
          </p>
        </div>
        <div className={scheduler?.enabled ? "scheduler-led active" : "scheduler-led"}>
          <span aria-hidden="true" />
          {scheduler?.enabled ? "Scheduler Online" : "Scheduler Paused"}
        </div>
      </div>

      <div className="control-body">
        <div className="control-fields">
          <label>
            <span>Product Selection</span>
            <div className="field-shell disabled-field">
              {icon("account_balance_wallet")}
              <input value="INDmoney Flow" disabled readOnly />
            </div>
          </label>
          <label>
            <span>Target Period</span>
            <div className="field-shell">
              {icon("calendar_month")}
              <input
                value={isoWeek}
                onChange={(event) => setIsoWeek(event.target.value)}
                placeholder="2026-W17 or leave current"
              />
            </div>
          </label>
          <label>
            <span>Delivery Mode</span>
            <button
              type="button"
              className={draftOnly ? "mode-toggle active" : "mode-toggle"}
              onClick={() => setDraftOnly((value) => !value)}
            >
              {icon(draftOnly ? "edit_note" : "send")}
              {draftOnly ? "Draft Only" : "Send Enabled"}
            </button>
          </label>
        </div>

        <div className="control-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={busyAction !== ""}
            onClick={toggleScheduler}
          >
            {icon("event_repeat")}
            {busyAction === "scheduler"
              ? "Updating..."
              : scheduler?.enabled
                ? "Disable Periodic Scheduler"
                : "Enable Periodic Scheduler"}
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={busyAction !== ""}
            onClick={triggerSingleRun}
          >
            {icon("play_arrow")}
            {busyAction === "run" ? "Submitting..." : "Run INDMoney Flow Once"}
          </button>
        </div>
      </div>

      <div className="csv-upload-box">
        <div className="csv-upload-copy">
          <div className="csv-upload-icon">{icon("upload_file")}</div>
          <div>
            <p className="eyebrow tiny">CSV Upload</p>
            <h3>Upload CSV and run the same Docs + Gmail flow</h3>
            <p className="muted">
              Include a review text column such as <code>review</code>, <code>body</code>, or
              <code>feedback</code>. Optional columns: rating, title, reviewed_at, locale.
            </p>
          </div>
        </div>
        <div className="csv-upload-actions">
          <label className="file-picker">
            {icon("attach_file")}
            <span>{csvFile ? csvFile.name : "Choose CSV file"}</span>
            <input
              accept=".csv,text/csv"
              type="file"
              onChange={(event) => setCsvFile(event.target.files?.[0] || null)}
            />
          </label>
          <button
            type="button"
            className="secondary-button"
            disabled={busyAction !== ""}
            onClick={uploadCsvAndRun}
          >
            {icon("cloud_upload")}
            {busyAction === "csv" ? "Uploading..." : "Upload CSV & Run Flow"}
          </button>
        </div>
      </div>

      <div className="control-footer">
        <span>Browser date reference: {defaultWeek}</span>
        <span>Recipient: gptshivam595@gmail.com</span>
      </div>
      {status ? <p className="status-banner">{status}</p> : null}
    </section>
  );
}
