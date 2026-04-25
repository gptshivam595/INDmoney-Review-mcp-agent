"use client";

import { useState } from "react";

const defaultWeek = new Date().toISOString().slice(0, 10);
const operatorProductKey = "indmoney";

export function TriggerPanel({ apiBaseUrl, scheduler }) {
  const [isoWeek, setIsoWeek] = useState("");
  const [draftOnly, setDraftOnly] = useState(true);
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
        `Queued INDMoney flow ${payload.job.job_id}. Watch the Background Jobs and Delivery Audit panels for progress.`,
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

  return (
    <section className="panel accent-panel">
      <div className="panel-header">
        <p className="eyebrow">INDMoney Control</p>
        <h2>Run one flow now or control the periodic scheduler for INDMoney only</h2>
      </div>
      <div className="form-grid compact">
        <label>
          <span>Product</span>
          <input value="INDMoney" disabled readOnly />
        </label>
        <label>
          <span>ISO week</span>
          <input
            value={isoWeek}
            onChange={(event) => setIsoWeek(event.target.value)}
            placeholder="2026-W17"
          />
        </label>
        <label className="toggle-row">
          <span>Draft only</span>
          <button
            type="button"
            className={draftOnly ? "toggle active" : "toggle"}
            onClick={() => setDraftOnly((value) => !value)}
          >
            {draftOnly ? "Enabled" : "Disabled"}
          </button>
        </label>
      </div>
      <div className="button-row">
        <button
          type="button"
          className="primary-button"
          disabled={busyAction !== ""}
          onClick={triggerSingleRun}
        >
          {busyAction === "run" ? "Submitting..." : "Run INDMoney Flow Once"}
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={busyAction !== ""}
          onClick={toggleScheduler}
        >
          {busyAction === "scheduler"
            ? "Updating..."
            : scheduler?.enabled
              ? "Disable Periodic Scheduler"
              : "Enable Periodic Scheduler"}
        </button>
      </div>
      <p className="muted">
        One-shot flow runs ingestion, analysis, OpenAI summarization, render, Docs publish, and
        Gmail draft/send for INDMoney. The periodic scheduler control updates the backend schedule
        state for INDMoney only. Browser date reference: {defaultWeek}.
      </p>
      {status ? <p className="status-banner">{status}</p> : null}
    </section>
  );
}
