import type { ProspectRun } from "../api/schemas";
import { ACTIVE_RUN_STORAGE_KEY } from "./constants";

function shouldRemember(run: ProspectRun) {
  return run.status === "queued" || run.status === "running" || run.status === "awaiting_review";
}

function key(subject: string) {
  return `${ACTIVE_RUN_STORAGE_KEY}:${subject}`;
}

export function storedRunId(subject: string) {
  try {
    const scoped = window.sessionStorage.getItem(key(subject));
    if (scoped) return scoped;
    if (subject === "test-user") {
      const legacy = window.sessionStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
      if (legacy) {
        window.sessionStorage.setItem(key(subject), legacy);
        window.sessionStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
        return legacy;
      }
    }
    return undefined;
  } catch {
    return undefined;
  }
}

export function rememberRun(subject: string, run: ProspectRun | undefined) {
  try {
    if (run && shouldRemember(run)) {
      window.sessionStorage.setItem(key(subject), run.id);
    } else {
      window.sessionStorage.removeItem(key(subject));
      if (subject === "test-user") window.sessionStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    }
  } catch {
    // A blocked session store must not prevent the durable server-side run from continuing.
  }
}

export function clearRememberedRun(subject: string) {
  try {
    window.sessionStorage.removeItem(key(subject));
  } catch {
    // Logout still clears the server session when browser storage is unavailable.
  }
}
