import type { ProspectRun } from "../api/schemas";
import { ACTIVE_RUN_STORAGE_KEY } from "./constants";

function shouldRemember(run: ProspectRun) {
  return run.status === "queued" || run.status === "running" || run.status === "awaiting_review";
}

export function storedRunId() {
  try {
    return window.sessionStorage.getItem(ACTIVE_RUN_STORAGE_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

export function rememberRun(run: ProspectRun | undefined) {
  try {
    if (run && shouldRemember(run)) {
      window.sessionStorage.setItem(ACTIVE_RUN_STORAGE_KEY, run.id);
    } else {
      window.sessionStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    }
  } catch {
    // A blocked session store must not prevent the durable server-side run from continuing.
  }
}
