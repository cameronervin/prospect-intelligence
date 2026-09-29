import { z } from "zod";

const BackendUrl = z.url();

export function backendBaseUrl(environment: NodeJS.ProcessEnv = process.env): string {
  return BackendUrl.parse(environment.BACKEND_BASE_URL ?? "http://127.0.0.1:8000");
}
