"use client";

import { useEffect, useState } from "react";

import { TriggerPanel } from "./trigger-panel";

function StatCard({ label, value, tone = "default", helper = "" }) {
  return (
    <article className={`stat-card ${tone}`}>
      <p>{label}</p>
      <strong>{value}</strong>
      {helper ? <span>{helper}</span> : null}
    </article>
  );
}

function SectionHeader({ eyebrow, title, description = "" }) {
  return (
    <div className="panel-header">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {description ? <p className="muted">{description}</p> : null}
    </div>
  );
}

function ServiceGrid({ services = [] }) {
  if (!services.length) {
    return <p className="empty-state">No service data available.</p>;
  }

  return (
    <div className="service-grid">
      {services.map((service) => (
        <article key={service.key} className="service-card">
          <div className="service-card-top">
            <div>
              <p className="eyebrow small">{service.label}</p>
              <h3>{service.status}</h3>
            </div>
            <span className={`pill pill-${service.status}`}>{service.status}</span>
          </div>
          <p className="muted">{service.detail}</p>
        </article>
      ))}
    </div>
  );
}

function IssuesPanel({ issues }) {
  const warnings = issues?.warnings || [];
  const errors = issues?.errors || [];

  return (
    <div className="issue-columns">
      <div>
        <p className="eyebrow small">Warnings</p>
        {warnings.length ? (
          <div className="issue-stack">
            {warnings.map((warning) => (
              <article key={warning.code} className="issue-card warning">
                <strong>{warning.title}</strong>
                <p>{warning.detail}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-state">No warnings right now.</p>
        )}
      </div>
      <div>
        <p className="eyebrow small">Errors</p>
        {errors.length ? (
          <div className="issue-stack">
            {errors.map((error, index) => (
              <article key={`${error.code}-${index}`} className="issue-card error">
                <strong>{error.title}</strong>
                <p>{error.detail}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-state">No active errors right now.</p>
        )}
      </div>
    </div>
  );
}

function FleetGrid({ fleet = [] }) {
  if (!fleet.length) {
    return <p className="empty-state">No fleet records found.</p>;
  }

  return (
    <div className="fleet-grid">
      {fleet.map((product) => (
        <article key={product.product_key} className="fleet-card">
          <div className="fleet-top">
            <div>
              <p className="eyebrow small">{product.product_key}</p>
              <h3>{product.display_name}</h3>
            </div>
            <span className={`pill pill-${product.latest_status}`}>{product.latest_status}</span>
          </div>
          <p className="muted">{product.latest_detail}</p>
          <div className="fleet-meta">
            <span>Stakeholders: {product.stakeholder_count}</span>
            <span>Last run: {product.latest_started_at || "Never"}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function RunTable({ runs = [] }) {
  if (!runs.length) {
    return <p className="empty-state">No runs recorded yet.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Week</th>
            <th>Status</th>
            <th>Started</th>
            <th>Delivery</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <td>{run.product_key}</td>
              <td>{run.iso_week}</td>
              <td>
                <span className={`pill pill-${run.status}`}>{run.status}</span>
              </td>
              <td>{run.started_at}</td>
              <td>{run.gmail_message_id || run.gmail_draft_id || run.gdoc_deep_link || "Pending"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobList({ jobs = [] }) {
  if (!jobs.length) {
    return <p className="empty-state">No active or queued jobs.</p>;
  }

  return (
    <div className="job-stack">
      {jobs.map((job) => (
        <article key={job.job_id} className="job-card">
          <div className="job-top">
            <div>
              <p className="job-kind">{job.kind}</p>
              <h3>{job.product_key || "all-active-products"}</h3>
            </div>
            <span className={`pill pill-${job.status}`}>{job.status}</span>
          </div>
          <p className="muted">Week: {job.iso_week || "current"}</p>
          <p className="muted">Run ids: {job.run_ids?.length ? job.run_ids.join(", ") : "pending"}</p>
          {job.error_message ? <p className="error-text">{job.error_message}</p> : null}
        </article>
      ))}
    </div>
  );
}

function DeliveryTable({ events = [] }) {
  if (!events.length) {
    return <p className="empty-state">No delivery events recorded yet.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Channel</th>
            <th>Status</th>
            <th>Run</th>
            <th>Occurred</th>
            <th>External Id</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.event_id}>
              <td>{event.channel}</td>
              <td>
                <span className={`pill pill-${event.status}`}>{event.status}</span>
              </td>
              <td>{event.run_id}</td>
              <td>{event.occurred_at}</td>
              <td>{event.external_id || "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DashboardShell({ apiBaseUrl }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/dashboard`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const nextPayload = await response.json();
        if (!active) {
          return;
        }
        setPayload(nextPayload);
        setError("");
        setLastUpdated(new Date().toLocaleTimeString());
      } catch (nextError) {
        if (!active) {
          return;
        }
        setError(nextError instanceof Error ? nextError.message : "Unknown dashboard failure");
      }
    }

    load();
    const intervalId = window.setInterval(load, 15000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [apiBaseUrl]);

  const counts = payload?.counts || {};
  const auth = payload?.google_auth || {};
  const scheduler = payload?.scheduler || {};
  const products = payload?.products || [];
  const services = payload?.services || [];
  const issues = payload?.issues || { warnings: [], errors: [] };
  const fleet = payload?.fleet || [];
  const runs = payload?.recent_runs || [];
  const jobs = payload?.jobs || [];
  const events = payload?.recent_delivery_events || [];

  return (
    <main className="shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Operations Control Tower</p>
          <h1>Live pulse health for agents, services, schedule, and delivery risk.</h1>
          <p className="hero-text">
            This dashboard auto-refreshes every 15 seconds and gives operators one place to check
            whether the weekly review pulse is healthy, blocked, or ready for a one-shot run.
          </p>
          <div className="hero-meta">
            <span>API: <code>{apiBaseUrl}</code></span>
            <span>Last updated: {lastUpdated || "waiting"}</span>
          </div>
          {error ? <p className="error-banner">{error}</p> : null}
        </div>
        <div className="hero-grid">
          <StatCard label="Products" value={counts.products ?? 0} tone="amber" />
          <StatCard label="Runs" value={counts.runs ?? 0} helper="Historical executions" />
          <StatCard label="Reviews" value={counts.reviews ?? 0} tone="teal" helper="Stored input rows" />
          <StatCard
            label="Issues"
            value={(issues.warnings?.length || 0) + (issues.errors?.length || 0)}
            tone={(issues.errors?.length || 0) > 0 ? "rose" : "amber"}
            helper="Warnings + errors"
          />
        </div>
      </section>

      <section className="panel-strip triple">
        <section className="panel">
          <SectionHeader
            eyebrow="Service Health"
            title="Live backend and delivery status"
            description="Green means active, amber means attention needed, and red means the operator should intervene."
          />
          <ServiceGrid services={services} />
        </section>

        <section className="panel">
          <SectionHeader
            eyebrow="Scheduler"
            title={scheduler.status || "inactive"}
            description="Recurring cadence is metadata-driven here; Railway cron or another external scheduler should drive the actual periodic trigger."
          />
          <div className="scheduler-grid">
            <StatCard label="Cadence" value={scheduler.cadence_label || "Not configured"} tone="amber" />
            <StatCard label="Timezone" value={scheduler.timezone || "n/a"} />
            <StatCard label="Next local run" value={scheduler.next_run_local || "Not scheduled"} tone="teal" />
            <StatCard label="Next UTC run" value={scheduler.next_run_utc || "Not scheduled"} />
          </div>
        </section>

        <section className="panel">
          <SectionHeader
            eyebrow="Issue Tracker"
            title="Warnings and errors"
            description="This tracker rolls up auth, send gating, scheduler state, and recent failed runs."
          />
          <IssuesPanel issues={issues} />
        </section>
      </section>

      <TriggerPanel apiBaseUrl={apiBaseUrl} products={products} />

      <section className="content-grid">
        <section className="panel">
          <SectionHeader
            eyebrow="Product Fleet"
            title="App coverage and latest run state"
            description="This gives you a quick product-by-product view of what is active and what last happened."
          />
          <FleetGrid fleet={fleet} />
        </section>

        <section className="panel">
          <SectionHeader
            eyebrow="Auth and Delivery Readiness"
            title="Google workspace readiness"
            description="These are the main runtime prerequisites for a real end-to-end docs plus Gmail flow."
          />
          <div className="readiness-grid">
            <StatCard
              label="Google token"
              value={auth.token_available ? "available" : "missing"}
              tone={auth.token_available ? "teal" : "rose"}
            />
            <StatCard
              label="Client ID"
              value={auth.client_id_present ? "set" : "missing"}
              tone={auth.client_id_present ? "teal" : "rose"}
            />
            <StatCard
              label="Client secret"
              value={auth.client_secret_present ? "set" : "missing"}
              tone={auth.client_secret_present ? "teal" : "rose"}
            />
            <StatCard
              label="Profile"
              value={auth.profile || "default"}
              tone="amber"
              helper={auth.token_source || ""}
            />
          </div>
        </section>
      </section>

      <section className="content-grid">
        <section className="panel">
          <SectionHeader
            eyebrow="Recent Runs"
            title="Latest pipeline history"
            description="Use this to spot incomplete runs, repeated failures, and successful one-shot flows."
          />
          <RunTable runs={runs} />
        </section>

        <section className="panel">
          <SectionHeader
            eyebrow="Background Jobs"
            title="Queued and running work"
            description="One-shot buttons create jobs here so you can track them without watching the terminal."
          />
          <JobList jobs={jobs} />
        </section>
      </section>

      <section className="panel">
        <SectionHeader
          eyebrow="Delivery Audit"
          title="Recent Docs and Gmail events"
          description="This is the quick audit trail for stakeholder-visible delivery actions."
        />
        <DeliveryTable events={events} />
      </section>
    </main>
  );
}
