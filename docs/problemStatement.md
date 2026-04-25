# Weekly Product Review Pulse - Problem Statement

## 1. Problem

Teams need a dependable weekly view of what customers are saying in public app reviews, but today that insight is usually assembled by hand, inconsistently, and without a durable archive.

The practical pain points are:

- Apple App Store and Google Play feedback live in separate places
- raw reviews are noisy and hard to summarize quickly
- manual copy-paste into docs and email is brittle
- historical context gets lost when updates are shared ad hoc

## 2. Product We Are Building

We are building an AI agent called **Weekly Product Review Pulse**.

The agent must:

1. fetch recent reviews from App Store and Play Store
2. analyze and cluster those reviews
3. summarize the key themes into a compact weekly pulse
4. append that pulse into a running Google Doc
5. notify stakeholders by Gmail with a link to the new section
6. expose an internal dashboard so operators can inspect status and trigger runs

## 3. Initial Product Scope

The highest-priority configured product is now:

- INDMoney

Configured sources:

- App Store: `https://apps.apple.com/in/app/indmoney-stocks-mutual-funds/id1450178837`
- Play Store: `https://play.google.com/store/apps/details?id=in.indwealth&hl=en_IN`

Configured notification target:

- `gptshivam595@gmail.com`

## 4. Desired Outcome

Stakeholders should receive one consistent weekly pulse that includes:

- top customer themes
- grounded representative quotes
- suggested product or support actions
- a short explanation of who the findings help

The long-term archive should live in one running Google Doc per product.

## 5. Functional Requirements

The system must:

- support a rolling 8-12 week review window
- ingest both App Store and Play Store reviews
- scrub PII before reasoning or publication
- cluster related feedback into actionable themes
- generate a concise weekly report
- render a Docs payload and Gmail payload
- append the weekly report exactly once for a given product plus ISO week
- draft or send the Gmail notification exactly once for that same run
- support manual run triggers and weekly batch execution
- preserve audit data for every run

## 6. Operator Requirements

Operators need an internal surface that can:

- show service health
- show whether Google auth is ready
- show recent runs and delivery outcomes
- show queued and in-flight jobs
- trigger a single-product run
- trigger a weekly batch run

This dashboard is not the stakeholder-facing report surface. It is only for operations.

## 7. Safety Requirements

- review text must be treated as untrusted input
- quotes must be validated against real stored review text
- failures must be explicit rather than silent
- send mode must stay gated until Docs delivery is working

## 8. What “Complete” Means

The project is only truly complete end to end when:

- the weekly run ingests INDMoney reviews from both stores
- the report is appended to the product Google Doc
- the stakeholder email is drafted or sent to `gptshivam595@gmail.com`
- rerunning the same week does not duplicate the Docs section or email
- operators can see the run from the dashboard and trigger it again safely

## 9. Current Truth in This Workspace

As of 2026-04-25:

- the codebase implements the ingestion, analysis, summarization, rendering, delivery, operator API, and dashboard layers
- the dashboard exists and builds successfully
- the backend API exists and responds successfully
- live Google delivery still depends on a valid OAuth token being present locally or in deployment

That means the repo is operationally close, but live Google completion is still auth-dependent.
