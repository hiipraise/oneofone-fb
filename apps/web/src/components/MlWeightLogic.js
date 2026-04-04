export const ML_ACTIVATION_THRESHOLD = 30

export function getMlWeightState(weight = 0, nSamples = 0) {
  const n = nSamples ?? 0
  const wPct = Math.round((weight ?? 0) * 100)
  const active = n >= ML_ACTIVATION_THRESHOLD

  const progressPct = Math.min(Math.round((n / ML_ACTIVATION_THRESHOLD) * 100), 100)

  // Keep these thresholds in sync with main panel behavior.
  const mlBarColor = wPct >= 60 ? 'bg-brand-green' : 'bg-yellow-500'
  const mlTextColor = wPct >= 60 ? 'text-brand-greenlight' : 'text-yellow-400'

  return {
    n,
    wPct,
    active,
    progressPct,
    mlBarColor,
    mlTextColor,
    threshold: ML_ACTIVATION_THRESHOLD,
  }
}
