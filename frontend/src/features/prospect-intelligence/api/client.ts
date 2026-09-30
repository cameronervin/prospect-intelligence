import { z } from "zod";

import {
  AccountsSchema,
  ErrorResponseSchema,
  RunSchema,
  type Account,
  type ErrorIssue,
  type ProspectApiErrorCode,
  type ProspectRun,
} from "./schemas";

export type RunReview = {
  decision: "approve" | "edit" | "reject";
  subject?: string;
  body?: string;
  tool_call_id: string;
};
export interface ProspectClient {
  listAccounts(): Promise<Account[]>;
  startRun(accountId: string): Promise<ProspectRun>;
  getRun(runId: string): Promise<ProspectRun>;
  reviewRun(runId: string, review: RunReview): Promise<ProspectRun>;
}
type ClientOptions = { fetcher?: typeof fetch; tenantId: string; repId: string };

export class ProspectApiError extends Error {
  readonly code?: ProspectApiErrorCode;
  readonly retryable?: boolean;
  readonly issues: ErrorIssue[];

  constructor(
    message = "The prospect service is unavailable",
    options: { code?: ProspectApiErrorCode; retryable?: boolean; issues?: ErrorIssue[] } = {},
  ) {
    super(message);
    this.name = "ProspectApiError";
    this.code = options.code;
    this.retryable = options.retryable;
    this.issues = options.issues ?? [];
  }
}

export function createProspectClient({
  fetcher = fetch,
  tenantId,
  repId,
}: ClientOptions): ProspectClient {
  const headers = {
    "Content-Type": "application/json",
    "X-Tenant-Id": tenantId,
    "X-Rep-Id": repId,
  };
  async function request<T>(path: string, init: RequestInit, schema: z.ZodType<T>): Promise<T> {
    let response: Response;
    try {
      response = await fetcher(path, { ...init, headers: { ...headers, ...init.headers } });
    } catch {
      throw new ProspectApiError();
    }
    if (!response.ok) {
      const payload = await response
        .json()
        .then((body: unknown) => ErrorResponseSchema.safeParse(body))
        .catch(() => undefined);
      if (payload?.success) {
        throw new ProspectApiError(payload.data.error.message, {
          code: payload.data.error.code,
          retryable: payload.data.error.retryable,
          issues: payload.data.error.issues,
        });
      }
      throw new ProspectApiError(`The prospect service returned ${response.status}`);
    }
    try {
      return schema.parse(await response.json());
    } catch {
      throw new ProspectApiError("The prospect service returned an invalid response");
    }
  }
  return {
    async listAccounts() {
      return (await request("/api/v1/accounts", { method: "GET" }, AccountsSchema)).items;
    },
    startRun(accountId) {
      return request(
        "/api/v1/prospect-runs",
        { method: "POST", body: JSON.stringify({ account_id: accountId }) },
        RunSchema,
      );
    },
    getRun(runId) {
      return request(
        `/api/v1/prospect-runs/${encodeURIComponent(runId)}`,
        { method: "GET" },
        RunSchema,
      );
    },
    reviewRun(runId, review) {
      return request(
        `/api/v1/prospect-runs/${encodeURIComponent(runId)}/review`,
        { method: "POST", body: JSON.stringify(review) },
        RunSchema,
      );
    },
  };
}
