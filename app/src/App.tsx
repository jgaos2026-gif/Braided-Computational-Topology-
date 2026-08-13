import { useEffect, useMemo, useState } from 'react'
import './App.css'
import {
  braidFeed,
  type BraidSnapshot,
  type OasisMetric,
  type OasisNode,
  type VerificationState,
} from './braid'

const verificationLabel: Record<VerificationState, string> = {
  trusted: 'Trusted',
  verifying: 'Verifying',
  isolated: 'Isolated',
}

function formatLastUpdated(timestamp: string) {
  const seconds = Math.max(
    0,
    Math.round((Date.now() - new Date(timestamp).getTime()) / 1000),
  )

  if (seconds < 5) {
    return 'just now'
  }

  if (seconds < 60) {
    return `${seconds}s ago`
  }

  return `${Math.round(seconds / 60)}m ago`
}

function formatTrend(trend: number) {
  if (trend === 0) {
    return 'steady'
  }

  const direction = trend > 0 ? 'up' : 'down'
  return `${direction} ${Math.abs(trend).toFixed(1)}%`
}

function formatMetric(metric: OasisMetric) {
  return `${metric.value.toFixed(1)}${metric.unit}`
}

function App() {
  const [snapshot, setSnapshot] = useState<BraidSnapshot>(() =>
    braidFeed.getSnapshot(),
  )
  const [selectedId, setSelectedId] = useState<string>(
    () => braidFeed.getSnapshot().nodes[0]?.id ?? '',
  )

  useEffect(() => {
    return braidFeed.subscribe((nextSnapshot) => {
      setSnapshot(nextSnapshot)
      setSelectedId((current) => {
        if (nextSnapshot.nodes.some((node) => node.id === current)) {
          return current
        }

        return nextSnapshot.nodes[0]?.id ?? ''
      })
    })
  }, [])

  const selectedNode = useMemo<OasisNode | undefined>(
    () => snapshot.nodes.find((node) => node.id === selectedId),
    [selectedId, snapshot.nodes],
  )

  return (
    <main className="phone-shell">
      <section className="hero-panel">
        <div className="hero-topline">
          <span className="pill">Braid live</span>
          <span className={`pill pill-${snapshot.summary.overallHealth}`}>
            {snapshot.summary.overallHealth.replace('-', ' ')}
          </span>
        </div>
        <h1>Braid remote view</h1>
        <p className="hero-copy">
          One live braid connects every oasis, separates trusted from degraded
          readings, and keeps decision numbers moving without refresh.
        </p>
        <div className="hero-metrics">
          <article>
            <span className="metric-label">Decision index</span>
            <strong>{snapshot.summary.decisionIndex}</strong>
          </article>
          <article>
            <span className="metric-label">Trusted nodes</span>
            <strong>{snapshot.summary.trustedCount}</strong>
          </article>
          <article>
            <span className="metric-label">Active alerts</span>
            <strong>{snapshot.summary.alertCount}</strong>
          </article>
        </div>
        <div className="braid-strip">
          <div>
            <span className="metric-label">Braid pulse</span>
            <strong>{snapshot.summary.braidPulse.toFixed(0)}%</strong>
          </div>
          <div>
            <span className="metric-label">Last mesh update</span>
            <strong>{formatLastUpdated(snapshot.updatedAt)}</strong>
          </div>
        </div>
      </section>

      <section className="summary-grid" aria-label="Braid summary">
        <article className="summary-card">
          <span className="metric-label">Verifying</span>
          <strong>{snapshot.summary.verifyingCount}</strong>
          <p>Readings are visible but not yet certified into the braid totals.</p>
        </article>
        <article className="summary-card">
          <span className="metric-label">Isolated</span>
          <strong>{snapshot.summary.isolatedCount}</strong>
          <p>Unknown data is quarantined until repeated checks restore trust.</p>
        </article>
        <article className="summary-card">
          <span className="metric-label">Braid flow</span>
          <strong>{snapshot.contract.feed}</strong>
          <p>Every oasis publishes to the same shared contract.</p>
        </article>
      </section>

      <section className="section-header">
        <div>
          <h2>Oasis nodes</h2>
          <p>Tap a node for live detail and decision context.</p>
        </div>
      </section>

      <section className="node-list" aria-label="Oasis nodes">
        {snapshot.nodes.map((node) => (
          <button
            type="button"
            key={node.id}
            className={`node-card ${selectedId === node.id ? 'selected' : ''}`}
            onClick={() => setSelectedId(node.id)}
          >
            <div className="node-card-top">
              <div>
                <strong>{node.name}</strong>
                <span>{node.region}</span>
              </div>
              <span className={`status-dot ${node.health}`}></span>
            </div>
            <div className="node-card-state">
              <span className={`pill pill-${node.verification}`}>
                {verificationLabel[node.verification]}
              </span>
              <span>{formatLastUpdated(node.lastUpdated)}</span>
            </div>
            <div className="node-card-metrics">
              {node.metrics.slice(0, 3).map((metric) => (
                <div key={metric.key}>
                  <span>{metric.label}</span>
                  <strong>{formatMetric(metric)}</strong>
                </div>
              ))}
            </div>
            <p className="node-card-alert">
              {node.exceptions[0] ?? 'No active exceptions'}
            </p>
          </button>
        ))}
      </section>

      {selectedNode ? (
        <section className="detail-panel" aria-label={`${selectedNode.name} detail`}>
          <div className="detail-header">
            <div>
              <h2>{selectedNode.name}</h2>
              <p>
                {selectedNode.region} · {selectedNode.health.replace('-', ' ')} ·{' '}
                {verificationLabel[selectedNode.verification]}
              </p>
            </div>
            <span className={`pill pill-${selectedNode.verification}`}>
              {selectedNode.verification === 'trusted'
                ? 'Decision ready'
                : 'Use caution'}
            </span>
          </div>

          <div className="detail-grid">
            {selectedNode.metrics.map((metric) => (
              <article key={metric.key} className={`metric-card ${metric.status}`}>
                <span>{metric.label}</span>
                <strong>{formatMetric(metric)}</strong>
                <small>
                  Trend {formatTrend(metric.trend)} · Threshold{' '}
                  {metric.threshold.toFixed(0)}
                  {metric.unit}
                </small>
              </article>
            ))}
          </div>

          <div className="decision-band">
            <div>
              <span className="metric-label">Verification rule</span>
              <strong>{selectedNode.verificationRule}</strong>
            </div>
            <div>
              <span className="metric-label">Updated</span>
              <strong>{formatLastUpdated(selectedNode.lastUpdated)}</strong>
            </div>
          </div>

          <div className="exceptions-panel">
            <h3>Decision exceptions</h3>
            <ul>
              {selectedNode.exceptions.map((exception) => (
                <li key={exception}>{exception}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      <section className="contract-panel" aria-label="Braid contract">
        <h2>Minimum braid contract</h2>
        <dl>
          <div>
            <dt>oasisId</dt>
            <dd>Unique node identity for routing and comparison.</dd>
          </div>
          <div>
            <dt>metrics</dt>
            <dd>Current numeric signals, thresholds, and trend values.</dd>
          </div>
          <div>
            <dt>healthState</dt>
            <dd>Healthy, Phoenix alert, self-healing, or degraded.</dd>
          </div>
          <div>
            <dt>verificationState</dt>
            <dd>Trusted, verifying, or isolated before braid promotion.</dd>
          </div>
          <div>
            <dt>lastUpdated</dt>
            <dd>Timestamp used to spot stale live data fast.</dd>
          </div>
        </dl>
      </section>
    </main>
  )
}

export default App
