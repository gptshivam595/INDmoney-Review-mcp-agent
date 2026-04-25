"use client";

import { useEffect, useState } from "react";

import { TriggerPanel } from "./trigger-panel";

const operatorProductKey = "indmoney";

function icon(name, className = "") {
  return <span className={`material-symbols-outlined ${className}`}>{name}</span>;
}

function statusClass(status = "unknown") {
  return String(status)
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_");
}

function StatusPill({ status = "unknown", pulse = false }) {
  return (
    <span className={`status-pill status-${statusClass(status)} ${pulse ? "pulse" : ""}`}>
      <span aria-hidden="true" />
      {status}
    </span>
  );
}

function MetricTile({ label, value, helper = "", tone = "default", iconName = "analytics" }) {
  return (
    <article className={`metric-tile tone-${tone}`}>
      <div className="metric-icon">{icon(iconName)}</div>
      <p>{label}</p>
      <strong>{value}</strong>
      {helper ? <span>{helper}</span> : null}
    </article>
  );
}

function CommandPanel({
  eyebrow,
  title,
  description = "",
  iconName = "terminal",
  children,
  className = "",
  id = "",
}) {
  return (
    <section className={`command-panel ${className}`} id={id || undefined}>
      <div className="panel-chrome" aria-hidden="true" />
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>
            {icon(iconName)}
            {title}
          </h2>
          {description ? <p className="muted">{description}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function EmptyState({ children }) {
  return <p className="empty-state">{children}</p>;
}

function ServiceGrid({ services = [] }) {
  if (!services.length) {
    return <EmptyState>No service data available.</EmptyState>;
  }

  return (
    <div className="service-grid">
      {services.map((service) => (
        <article key={service.key} className="readiness-card">
          <div className="readiness-card-top">
            <div className="readiness-icon">{icon("dns")}</div>
            <StatusPill status={service.status} pulse={service.status === "active"} />
          </div>
          <p className="eyebrow tiny">{service.label}</p>
          <h3>{service.status}</h3>
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
        <div className="mini-heading">
          {icon("warning")}
          <span>Warnings</span>
        </div>
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
          <EmptyState>No warnings right now.</EmptyState>
        )}
      </div>
      <div>
        <div className="mini-heading">
          {icon("error")}
          <span>Errors</span>
        </div>
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
          <EmptyState>No active errors right now.</EmptyState>
        )}
      </div>
    </div>
  );
}

function LatestRunState({ fleet = [], runs = [] }) {
  const latestProduct = fleet[0];
  const latestRun = runs[0];

  if (!latestProduct && !latestRun) {
    return <EmptyState>No INDMoney runs recorded yet.</EmptyState>;
  }

  const status = latestRun?.status || latestProduct?.latest_status || "idle";
  const detail = latestProduct?.latest_detail || "Waiting for the next INDMoney execution.";

  return (
    <div className="latest-state">
      <div className="execution-row">
        <div>
          <p className="eyebrow tiny">Product</p>
          <strong>{latestProduct?.display_name || "INDmoney"}</strong>
        </div>
        <StatusPill status={status} pulse={status === "running" || status === "queued"} />
      </div>
      <p className="muted">{detail}</p>
      <div className="state-grid">
        <MetricTile
          label="Latest week"
          value={latestRun?.iso_week || "current"}
          helper="Target period"
          tone="gold"
          iconName="calendar_month"
        />
        <MetricTile
          label="Started"
          value={latestRun?.started_at || latestProduct?.latest_started_at || "Never"}
          helper="Backend timestamp"
          iconName="schedule"
        />
        <MetricTile
          label="Stakeholders"
          value={latestProduct?.stakeholder_count ?? 1}
          helper="INDmoney recipient list"
          tone="green"
          iconName="group"
        />
        <MetricTile
          label="Delivery"
          value={latestRun?.gmail_message_id || latestRun?.gmail_draft_id ? "ready" : "pending"}
          helper={latestRun?.gmail_message_id || latestRun?.gmail_draft_id || "No Gmail id yet"}
          tone={latestRun?.gmail_message_id || latestRun?.gmail_draft_id ? "green" : "gold"}
          iconName="outgoing_mail"
        />
      </div>
    </div>
  );
}

function ReadinessPanel({ auth = {}, checks = {} }) {
  const docs = checks?.docs;
  const gmail = checks?.gmail;
  const cards = [
    {
      label: "Configuration",
      title: "Google Token",
      status: auth.token_available ? "ready" : "missing",
      detail: auth.token_source || "OAuth token required",
      iconName: "key",
    },
    {
      label: "Identity",
      title: "Client ID",
      status: auth.client_id_present ? "ready" : "missing",
      detail: auth.profile || "default profile",
      iconName: "badge",
    },
    {
      label: "Security",
      title: "Client Secret",
      status: auth.client_secret_present ? "ready" : "missing",
      detail: auth.client_secret_present ? "Configured" : "Required for Google auth",
      iconName: "password",
    },
    {
      label: "Docs Probe",
      title: docs?.label || "Google Docs",
      status: docs?.status || "unknown",
      detail: docs?.detail || "Waiting for backend check",
      iconName: "article",
    },
    {
      label: "Gmail Probe",
      title: gmail?.label || "Gmail",
      status: gmail?.status || "unknown",
      detail: gmail?.detail || "Waiting for backend check",
      iconName: "mail",
    },
    {
      label: "Delivery",
      title: "Recipient",
      status: "ready",
      detail: "gptshivam595@gmail.com",
      iconName: "alternate_email",
    },
  ];

  return (
    <div className="readiness-grid">
      {cards.map((card) => (
        <article key={`${card.label}-${card.title}`} className="readiness-card">
          <div className="readiness-card-top">
            <div className="readiness-icon">{icon(card.iconName)}</div>
            <StatusPill status={card.status} />
          </div>
          <p className="eyebrow tiny">{card.label}</p>
          <h3>{card.title}</h3>
          <p className="muted">{card.detail}</p>
        </article>
      ))}
    </div>
  );
}

function SchedulerSnapshot({ scheduler = {} }) {
  return (
    <div className="scheduler-snapshot">
      <MetricTile
        label="Scheduler"
        value={scheduler.enabled ? "enabled" : "disabled"}
        helper={scheduler.status || "No backend status"}
        tone={scheduler.enabled ? "green" : "default"}
        iconName="event_repeat"
      />
      <MetricTile
        label="Cadence"
        value={scheduler.cadence_label || "Not configured"}
        helper={scheduler.timezone || "Timezone unavailable"}
        tone="gold"
        iconName="cycle"
      />
      <MetricTile
        label="Next local run"
        value={scheduler.next_run_local || "Not scheduled"}
        helper={scheduler.next_run_utc ? `UTC ${scheduler.next_run_utc}` : "Waiting for schedule"}
        iconName="schedule"
      />
    </div>
  );
}

function RunTable({ runs = [] }) {
  if (!runs.length) {
    return <EmptyState>No runs recorded yet.</EmptyState>;
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
            <th>Delivery ID</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <td>
                <strong>{run.product_key}</strong>
                <span className="table-subtext">{run.run_id}</span>
              </td>
              <td>{run.iso_week}</td>
              <td>
                <StatusPill status={run.status} />
              </td>
              <td>{run.started_at}</td>
              <td className="mono-cell">
                {run.gmail_message_id || run.gmail_draft_id || run.gdoc_deep_link || "Pending"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobList({ jobs = [] }) {
  if (!jobs.length) {
    return <EmptyState>No active or queued jobs.</EmptyState>;
  }

  return (
    <div className="job-stack">
      {jobs.map((job) => (
        <article key={job.job_id} className="job-card">
          <div className="job-top">
            <div className="job-icon">{icon(job.status === "running" ? "sync" : "hourglass_empty")}</div>
            <div>
              <p className="eyebrow tiny">{job.kind}</p>
              <h3>{job.job_id}</h3>
              <p className="muted">{job.product_key || "all-active-products"}</p>
            </div>
            <StatusPill status={job.status} pulse={job.status === "running"} />
          </div>
          <div className="job-meta">
            <span>Week: {job.iso_week || "current"}</span>
            <span>Run ids: {job.run_ids?.length ? job.run_ids.join(", ") : "pending"}</span>
          </div>
          {job.error_message ? <p className="error-text">{job.error_message}</p> : null}
        </article>
      ))}
    </div>
  );
}

function DeliveryTable({ events = [] }) {
  if (!events.length) {
    return <EmptyState>No delivery events recorded yet.</EmptyState>;
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
            <th>External ID</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.event_id}>
              <td>{event.channel}</td>
              <td>
                <StatusPill status={event.status} />
              </td>
              <td>{event.run_id}</td>
              <td>{event.occurred_at}</td>
              <td className="mono-cell">{event.external_id || "n/a"}</td>
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
  const [refreshNonce, setRefreshNonce] = useState(0);

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
  }, [apiBaseUrl, refreshNonce]);

  const counts = payload?.counts || {};
  const auth = payload?.google_auth || {};
  const scheduler = payload?.scheduler || {};
  const workspaceChecks = payload?.mcp_checks || {};
  const services = payload?.services || [];
  const issues = payload?.issues || { warnings: [], errors: [] };
  const fleet = (payload?.fleet || []).filter((product) => product.product_key === operatorProductKey);
  const runs = (payload?.recent_runs || []).filter((run) => run.product_key === operatorProductKey);
  const jobs = (payload?.jobs || []).filter((job) => !job.product_key || job.product_key === operatorProductKey);
  const events = payload?.recent_delivery_events || [];
  const issueCount = (issues.warnings?.length || 0) + (issues.errors?.length || 0);
  const topStatus = error ? "degraded" : issueCount > 0 ? "attention" : "operational";

  return (
    <div className="command-app">
      <aside className="command-sidebar" aria-label="Command Center navigation">
        <div className="brand-lockup">
          <div className="brand-mark">{icon("dns")}</div>
          <div>
            <strong>Command Center</strong>
            <span>Lux-Tech Precision</span>
          </div>
        </div>
        <nav className="side-links">
          <a className="active" href="#overview">
            {icon("dashboard")}
            Dashboard
          </a>
          <a href="#runs">
            {icon("dns")}
            Server Nodes
          </a>
          <a href="#issues">
            {icon("terminal")}
            Log Terminal
          </a>
          <a href="#delivery">
            {icon("hub")}
            Network Mesh
          </a>
          <a href="#scheduler">
            {icon("settings_suggest")}
            Admin Settings
          </a>
        </nav>
        <div className="sidebar-footer">
          <button type="button" className="deploy-button">
            Deploy Instance
          </button>
          <a href="#issues">{icon("help_outline")} Support</a>
          <a href="#workspace">{icon("description")} System Docs</a>
        </div>
      </aside>

      <main className="command-main">
        <header className="top-bar">
          <div className="top-title">
            <span>INDmoney Server Health</span>
            <div className="search-box">
              {icon("search")}
              <input aria-label="Search resources" placeholder="Search resources..." type="text" />
            </div>
          </div>
          <div className="top-actions">
            <span className="environment-badge">PROD-ENVIRONMENT</span>
            <span className="last-updated">Last Updated: {lastUpdated || "waiting"}</span>
            <button
              type="button"
              aria-label="Refresh dashboard"
              onClick={() => setRefreshNonce((value) => value + 1)}
            >
              {icon("refresh")}
            </button>
            <button type="button" aria-label="Notifications" className="notification-button">
              {icon("notifications_active")}
              <span />
            </button>
            <div className="avatar" aria-hidden="true">
              IN
            </div>
          </div>
        </header>

        <div className="dashboard-canvas" id="overview">
          <section className="hero-panel">
            <div>
              <p className="eyebrow">Operations Control Tower</p>
              <h1>INDmoney Command Center</h1>
              <p className="hero-text">
                Live pulse health for INDMoney review ingestion, OpenAI summarization, Google Docs
                publishing, Gmail delivery, and scheduler risk.
              </p>
              <div className="hero-meta">
                <span>
                  API <code>{apiBaseUrl}</code>
                </span>
                <span>Auto-refresh 15s</span>
                <StatusPill status={topStatus} pulse={topStatus === "attention"} />
              </div>
              {error ? <p className="error-banner">Dashboard API error: {error}</p> : null}
            </div>
            <div className="hero-metrics">
              <MetricTile label="Products" value={counts.products ?? 0} helper="INDmoney exposed" tone="gold" iconName="inventory_2" />
              <MetricTile label="Runs" value={counts.runs ?? 0} helper="Historical executions" iconName="history" />
              <MetricTile label="Reviews" value={counts.reviews ?? 0} helper="Stored input rows" tone="green" iconName="reviews" />
              <MetricTile
                label="Issues"
                value={issueCount}
                helper="Warnings + errors"
                tone={(issues.errors?.length || 0) > 0 ? "red" : issueCount ? "gold" : "green"}
                iconName="release_alert"
              />
            </div>
          </section>

          <TriggerPanel apiBaseUrl={apiBaseUrl} scheduler={scheduler} />

          <div className="dashboard-grid two-up">
            <CommandPanel
              eyebrow="INDMoney Status"
              title="Latest INDMoney run state"
              description="Current operator view for the only product exposed in this dashboard."
              iconName="history"
            >
              <LatestRunState fleet={fleet} runs={runs} />
            </CommandPanel>

            <CommandPanel
              eyebrow="Auth and Delivery Readiness"
              title="Google Workspace checks"
              description="The runtime prerequisites for a real Docs plus Gmail delivery flow."
              iconName="verified_user"
              className="readiness-panel"
              id="workspace"
            >
              <ReadinessPanel auth={auth} checks={workspaceChecks} />
            </CommandPanel>
          </div>

          <div className="dashboard-grid two-up">
            <CommandPanel
              eyebrow="Service Health"
              title="Backend and delivery status"
              description="Google Docs, Gmail, MCP-style probes, and backend health roll up here."
              iconName="monitor_heart"
            >
              <ServiceGrid services={services} />
            </CommandPanel>

            <CommandPanel
              eyebrow="Scheduler"
              title="Periodic scheduler"
              description="Recurring cadence is controlled for INDMoney only. One-shot runs remain available."
              iconName="event_repeat"
            >
              <SchedulerSnapshot scheduler={scheduler} />
            </CommandPanel>
          </div>

          <CommandPanel
            eyebrow="Issue Tracker"
            title="Warnings and errors"
            description="This tracker surfaces Google Docs, Gmail, auth, MCP/server, scheduler, and failed-run problems."
            iconName="report"
            className="wide-panel"
            id="issues"
          >
            <IssuesPanel issues={issues} />
          </CommandPanel>

          <div className="dashboard-grid history-grid" id="runs">
            <CommandPanel
              eyebrow="Recent Runs"
              title="Latest pipeline history"
              description="Spot incomplete runs, repeated failures, and successful one-shot flows."
              iconName="table_chart"
              className="table-panel"
            >
              <RunTable runs={runs} />
            </CommandPanel>

            <CommandPanel
              eyebrow="Background Jobs"
              title="Queued and running work"
              description="One-shot buttons create jobs here so you can track them without a terminal."
              iconName="work_history"
            >
              <JobList jobs={jobs} />
            </CommandPanel>
          </div>

          <CommandPanel
            eyebrow="Delivery Audit"
            title="Recent Docs and Gmail events"
            description="Quick audit trail for stakeholder-visible delivery actions."
            iconName="fact_check"
            className="table-panel"
            id="delivery"
          >
            <DeliveryTable events={events} />
          </CommandPanel>
        </div>
      </main>
    </div>
  );
}
