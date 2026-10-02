type LogLevel = "debug" | "info" | "warning" | "error";
type LogFields = Record<string, unknown>;

const SENSITIVE_MARKERS = ["authorization", "cookie", "password", "secret", "token", "api_key"];
const SAFE_CORRELATION_ID = /^[A-Za-z0-9._-]{1,64}$/;

function isSensitive(key: string) {
  const normalized = key.toLowerCase().replaceAll("-", "_");
  return SENSITIVE_MARKERS.some((marker) => normalized.includes(marker));
}

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        isSensitive(key) ? "[REDACTED]" : redact(item),
      ]),
    );
  }
  return value;
}

export function correlationId(candidate: string | null | undefined): string {
  return candidate && SAFE_CORRELATION_ID.test(candidate) ? candidate : crypto.randomUUID();
}

export function serverLog(level: LogLevel, event: string, fields: LogFields = {}): void {
  const record = redact({
    timestamp: new Date().toISOString(),
    level,
    event,
    logger: "frontend.server",
    service: "langchain-takehome-frontend",
    environment: process.env.NODE_ENV ?? "unknown",
    ...fields,
  });
  const line = JSON.stringify(record);
  if (level === "error") console.error(line);
  else if (level === "warning") console.warn(line);
  else if (level === "debug") console.debug(line);
  else console.info(line);
}
