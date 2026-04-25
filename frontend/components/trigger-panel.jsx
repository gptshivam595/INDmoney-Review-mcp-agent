"use client";

import { useMemo, useState } from "react";

const defaultWeek = new Date().toISOString().slice(0, 10);

export function TriggerPanel({ apiBaseUrl, products }) {
  const activeProducts = useMemo(
    () => products.filter((product) => product.active),
    [products],
  );
  const [productKey, setProductKey] = useState(activeProducts[0]?.product_key ?? "indmoney");
  const [isoWeek, setIsoWeek] = useState("");
  const [draftOnly, setDraftOnly] = useState(true);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function trigger(path, body) {
    setBusy(true);
    setStatus("Submitting job...");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Request failed");
      }
      setStatus(`Queued ${payload.job.kind} job ${payload.job.job_id}. Refresh to see live status.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unknown request failure");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel accent-panel">
      <div className="panel-header">
        <p className="eyebrow">Command Center</p>
        <h2>Trigger a one-shot end-to-end flow without touching the terminal</h2>
      </div>
      <div className="form-grid">
        <label>
          <span>Product</span>
          <select value={productKey} onChange={(event) => setProductKey(event.target.value)}>
            {activeProducts.map((product) => (
              <option key={product.product_key} value={product.product_key}>
                {product.display_name}
              </option>
            ))}
          </select>
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
          disabled={busy}
          onClick={() =>
            trigger("/api/trigger/run", {
              product_key: productKey,
              iso_week: isoWeek || null,
              draft_only: draftOnly,
            })
          }
        >
          Run One-Shot Full Flow
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={() =>
            trigger("/api/trigger/weekly", {
              iso_week: isoWeek || null,
              draft_only: draftOnly,
            })
          }
        >
          Run Weekly Batch Now
        </button>
      </div>
      <p className="muted">
        One-shot full flow runs ingestion, analysis, summarization, render, Docs publish, and Gmail draft/send for the selected product. Leave ISO week blank to use the current week. Browser date reference: {defaultWeek}.
      </p>
      {status ? <p className="status-banner">{status}</p> : null}
    </section>
  );
}
