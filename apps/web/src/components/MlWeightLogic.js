export const ML_ACTIVATION_THRESHOLD = 30;

// ── Color thresholds (synchronized across all components) ─────────────────────
export const COLOR_THRESHOLD_HIGH = 60; // Green threshold for ML weight %
export const COLOR_THRESHOLD_MID = 30; // Yellow threshold for ML weight %
export const SAMPLE_THRESHOLD_CALIBRATION = 100; // Sample count for calibration method selection
export const SAMPLE_THRESHOLD_MID = 30; // Mid-tier sample threshold

// ── Calibration method selection ──────────────────────────────────────────────
export function getCalibrationMethod(nSamples) {
  if (nSamples >= SAMPLE_THRESHOLD_CALIBRATION) {
    return "isotonic";
  } else if (nSamples >= SAMPLE_THRESHOLD_MID) {
    return "sigmoid";
  } else {
    return "prior";
  }
}

// ── ML weight bar color selection ──────────────────────────────────────────────
export function getMlWeightBarColor(weightPercent) {
  if (weightPercent >= COLOR_THRESHOLD_HIGH) return "bg-brand-green";
  if (weightPercent >= COLOR_THRESHOLD_MID) return "bg-yellow-500";
  return "bg-brand-midgray";
}

// ── ML weight text color selection ─────────────────────────────────────────────
export function getMlWeightTextColor(weightPercent) {
  if (weightPercent >= COLOR_THRESHOLD_HIGH) return "text-brand-greenlight";
  if (weightPercent >= COLOR_THRESHOLD_MID) return "text-yellow-400";
  return "text-gray-600";
}

// ── Calibration display color ─────────────────────────────────────────────────
export function getCalibrationColor(nSamples) {
  if (nSamples >= SAMPLE_THRESHOLD_CALIBRATION) return "text-brand-greenlight";
  if (nSamples >= SAMPLE_THRESHOLD_MID) return "text-yellow-400";
  return "text-gray-600";
}

export function getMlWeightState(
  weight = 0,
  nSamples = 0,
  isTrained = false,
  threshold = ML_ACTIVATION_THRESHOLD,
) {
  const n = nSamples ?? 0;
  const activationThreshold = Math.max(threshold ?? ML_ACTIVATION_THRESHOLD, 1);
  const wPct = Math.round((weight ?? 0) * 100);
  const active = Boolean(isTrained);
  const readyToTrain = !active && n >= activationThreshold;

  const progressPct = Math.min(
    Math.round((n / activationThreshold) * 100),
    100,
  );

  // ── Use consolidated color functions ───────────────────────────────────────
  const mlBarColor = getMlWeightBarColor(wPct);
  const mlTextColor = getMlWeightTextColor(wPct);

  return {
    n,
    wPct,
    active,
    readyToTrain,
    progressPct,
    mlBarColor,
    mlTextColor,
    threshold: activationThreshold,
  };
}
