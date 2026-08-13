# Braid remote view

This app renders a compact remote dashboard for an iPhone 14 Pro Max-sized
viewport. It simulates a shared braid feed that connects all oasis nodes into
one live state.

## Commands

```bash
npm install
npm run dev
npm run lint
npm run build
```

## Data model

Each braid update publishes:

- `oasisId`
- `metrics` with values, thresholds, and trend
- `healthState`
- `verificationState`
- `lastUpdated`

The UI keeps verifying and isolated readings visible while excluding isolated
signals from trusted braid totals.
