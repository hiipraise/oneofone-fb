const WAT_TIME_ZONE = "Africa/Lagos";

export function formatWatDate(value, locale = "en-US") {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString(locale, { timeZone: WAT_TIME_ZONE });
  } catch {
    return String(value);
  }
}

export function formatWatTime(value, locale = "en-US") {
  if (!value) return "—";
  try {
    return `${new Date(value).toLocaleTimeString(locale, {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: WAT_TIME_ZONE,
    })} WAT`;
  } catch {
    return String(value);
  }
}

export function formatWatDateTime(value, locale = "en-US") {
  if (!value) return "—";
  try {
    return `${new Date(value).toLocaleString(locale, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: WAT_TIME_ZONE,
    })} WAT`;
  } catch {
    return String(value);
  }
}

export function watTodayISO() {
  const now = new Date();
  const watDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: WAT_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  return watDate;
}
