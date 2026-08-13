export type HealthState =
  | 'healthy'
  | 'phoenix-alert'
  | 'self-healing'
  | 'degraded'

export type VerificationState = 'trusted' | 'verifying' | 'isolated'
export type MetricStatus = 'stable' | 'watch' | 'critical'

export interface OasisMetric {
  key: string
  label: string
  unit: string
  value: number
  threshold: number
  trend: number
  status: MetricStatus
}

export interface OasisNode {
  id: string
  name: string
  region: string
  health: HealthState
  verification: VerificationState
  lastUpdated: string
  verificationRule: string
  metrics: OasisMetric[]
  exceptions: string[]
}

export interface BraidContract {
  feed: string
  version: string
}

export interface BraidSummary {
  overallHealth: HealthState
  trustedCount: number
  verifyingCount: number
  isolatedCount: number
  alertCount: number
  braidPulse: number
  decisionIndex: number
}

export interface BraidSnapshot {
  updatedAt: string
  contract: BraidContract
  summary: BraidSummary
  nodes: OasisNode[]
}

type Listener = (snapshot: BraidSnapshot) => void

const baseNodes: OasisNode[] = [
  createNode('oasis-north', 'North Oasis', 'Dune Ridge', 'healthy', 'trusted', [
    createMetric('flow', 'Flow', '%', 78, 82, 1.1, 'stable'),
    createMetric('reserve', 'Reserve', 'k', 42, 28, 0.4, 'stable'),
    createMetric('heat', 'Heat', '°', 31, 38, -0.6, 'stable'),
    createMetric('drift', 'Drift', 'ms', 12, 18, 0.2, 'stable'),
  ]),
  createNode(
    'oasis-east',
    'East Oasis',
    'Glass Channel',
    'phoenix-alert',
    'verifying',
    [
      createMetric('flow', 'Flow', '%', 66, 82, -1.9, 'watch'),
      createMetric('reserve', 'Reserve', 'k', 37, 28, -0.8, 'stable'),
      createMetric('heat', 'Heat', '°', 39, 38, 1.7, 'critical'),
      createMetric('drift', 'Drift', 'ms', 19, 18, 2.3, 'watch'),
    ],
  ),
  createNode(
    'oasis-south',
    'South Oasis',
    'Copper Basin',
    'self-healing',
    'trusted',
    [
      createMetric('flow', 'Flow', '%', 81, 82, 0.8, 'stable'),
      createMetric('reserve', 'Reserve', 'k', 33, 28, 1.9, 'stable'),
      createMetric('heat', 'Heat', '°', 34, 38, -0.2, 'stable'),
      createMetric('drift', 'Drift', 'ms', 15, 18, -0.4, 'stable'),
    ],
  ),
  createNode('oasis-west', 'West Oasis', 'Shadow Delta', 'degraded', 'isolated', [
    createMetric('flow', 'Flow', '%', 52, 82, -3.8, 'critical'),
    createMetric('reserve', 'Reserve', 'k', 21, 28, -1.2, 'watch'),
    createMetric('heat', 'Heat', '°', 43, 38, 2.9, 'critical'),
    createMetric('drift', 'Drift', 'ms', 24, 18, 2.6, 'critical'),
  ]),
]

function createMetric(
  key: string,
  label: string,
  unit: string,
  value: number,
  threshold: number,
  trend: number,
  status: MetricStatus,
): OasisMetric {
  return { key, label, unit, value, threshold, trend, status }
}

function createNode(
  id: string,
  name: string,
  region: string,
  health: HealthState,
  verification: VerificationState,
  metrics: OasisMetric[],
): OasisNode {
  return {
    id,
    name,
    region,
    health,
    verification,
    lastUpdated: new Date().toISOString(),
    verificationRule:
      verification === 'trusted'
        ? 'Certified after repeated braid agreement'
        : verification === 'verifying'
          ? 'Hold in review until three matching pulses'
          : 'Isolate unknown data from live decision totals',
    metrics,
    exceptions: buildExceptions(health, verification, metrics),
  }
}

function buildExceptions(
  health: HealthState,
  verification: VerificationState,
  metrics: OasisMetric[],
) {
  const exceptions = metrics
    .filter((metric) => metric.status !== 'stable')
    .map((metric) => {
      if (metric.status === 'critical') {
        return `${metric.label} breached threshold at ${metric.value.toFixed(1)}${metric.unit}`
      }

      return `${metric.label} is approaching its threshold`
    })

  if (verification === 'isolated') {
    exceptions.unshift('Braid totals exclude this node until trust is restored')
  } else if (verification === 'verifying') {
    exceptions.unshift('Recent readings are visible but remain outside certified totals')
  }

  if (health === 'self-healing') {
    exceptions.unshift('Self-healing braid path is active and reducing drift')
  }

  return exceptions.length > 0 ? exceptions : ['All signals are inside decision thresholds']
}

function nextMetric(metric: OasisMetric): OasisMetric {
  const drift = (Math.random() - 0.5) * 4
  const trend = Number((metric.trend * 0.6 + drift).toFixed(1))
  const value = Number(Math.max(0, metric.value + drift * 0.8).toFixed(1))
  const distance = metric.threshold - value
  const status: MetricStatus =
    distance <= 0 ? 'critical' : distance < metric.threshold * 0.1 ? 'watch' : 'stable'

  return {
    ...metric,
    trend,
    value,
    status,
  }
}

function rotateHealth(
  health: HealthState,
  verification: VerificationState,
  alertCount: number,
): HealthState {
  if (verification === 'isolated' || alertCount >= 3) {
    return 'degraded'
  }

  if (verification === 'verifying') {
    return alertCount >= 2 ? 'phoenix-alert' : 'self-healing'
  }

  if (health === 'self-healing' && alertCount === 0) {
    return 'healthy'
  }

  return alertCount > 0 ? 'self-healing' : 'healthy'
}

function rotateVerification(
  verification: VerificationState,
  alertCount: number,
): VerificationState {
  if (alertCount >= 3) {
    return 'isolated'
  }

  if (alertCount >= 1) {
    return verification === 'trusted' ? 'verifying' : verification
  }

  return verification === 'isolated' ? 'verifying' : 'trusted'
}

function evolveNode(node: OasisNode): OasisNode {
  const metrics = node.metrics.map(nextMetric)
  const alertCount = metrics.filter((metric) => metric.status !== 'stable').length
  const verification = rotateVerification(node.verification, alertCount)
  const health = rotateHealth(node.health, verification, alertCount)

  return {
    ...node,
    metrics,
    verification,
    health,
    lastUpdated: new Date().toISOString(),
    verificationRule:
      verification === 'trusted'
        ? 'Certified after repeated braid agreement'
        : verification === 'verifying'
          ? 'Hold in review until three matching pulses'
          : 'Isolate unknown data from live decision totals',
    exceptions: buildExceptions(health, verification, metrics),
  }
}

function summarize(nodes: OasisNode[]): BraidSummary {
  const trustedCount = nodes.filter((node) => node.verification === 'trusted').length
  const verifyingCount = nodes.filter((node) => node.verification === 'verifying').length
  const isolatedCount = nodes.filter((node) => node.verification === 'isolated').length
  const alertCount = nodes.reduce(
    (count, node) =>
      count + node.metrics.filter((metric) => metric.status !== 'stable').length,
    0,
  )
  const braidPulse = nodes.reduce(
    (sum, node) => sum + node.metrics.find((metric) => metric.key === 'flow')!.value,
    0,
  ) / nodes.length
  const decisionIndex = Math.max(
    0,
    Math.round(
      trustedCount * 25 +
        braidPulse -
        isolatedCount * 8 -
        Math.max(0, alertCount - verifyingCount) * 3,
    ),
  )

  const overallHealth: HealthState =
    isolatedCount > 0
      ? 'degraded'
      : verifyingCount > 0
        ? 'phoenix-alert'
        : alertCount > 0
          ? 'self-healing'
          : 'healthy'

  return {
    overallHealth,
    trustedCount,
    verifyingCount,
    isolatedCount,
    alertCount,
    braidPulse,
    decisionIndex,
  }
}

function createSnapshot(nodes: OasisNode[]): BraidSnapshot {
  return {
    updatedAt: new Date().toISOString(),
    contract: {
      feed: 'braid://oasis-live',
      version: '1.0',
    },
    summary: summarize(nodes),
    nodes,
  }
}

class BraidFeed {
  private listeners = new Set<Listener>()

  private snapshot = createSnapshot(baseNodes)

  private intervalId: number | null = null

  getSnapshot() {
    return this.snapshot
  }

  private start() {
    if (this.intervalId !== null) {
      return
    }

    this.intervalId = window.setInterval(() => {
      this.snapshot = createSnapshot(this.snapshot.nodes.map(evolveNode))
      this.listeners.forEach((listener) => listener(this.snapshot))
    }, 1800)
  }

  subscribe(listener: Listener) {
    this.start()
    this.listeners.add(listener)
    listener(this.snapshot)

    return () => {
      this.listeners.delete(listener)

      if (this.listeners.size === 0 && this.intervalId !== null) {
        window.clearInterval(this.intervalId)
        this.intervalId = null
      }
    }
  }
}

export const braidFeed = new BraidFeed()
