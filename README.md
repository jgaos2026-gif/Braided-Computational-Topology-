# Braided Computational Topology

Mobile-first braid dashboard for monitoring oasis nodes through one shared live
state.

## App

The remote view lives in
`/home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/app`.

### Run locally

```bash
cd /home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/app
npm install
npm run dev
```

### Validate

```bash
cd /home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/app
npm run lint
npm run build
```

## What the dashboard does

- Publishes every oasis into one braid feed: `braid://oasis-live`
- Tracks per-oasis metrics, trends, thresholds, health, and update time
- Separates trusted, verifying, and isolated data for safer live decisions
- Provides a compact iPhone 14 Pro Max-sized remote view plus a node detail view

## Minimum braid contract

- `oasisId`
- `metrics`
- `healthState`
- `verificationState`
- `lastUpdated`
