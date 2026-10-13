/**
 * Tek tip hata nesnesi ve yardımcısı (#46 / #10).
 * Backend ErrorResponse sözleşmesiyle birebir uyumludur:
 * { code, message, requestId, details? }
 */

export interface ApiErrorPayload {
  code: string;
  message: string;
  requestId: string | null;
  details?: Record<string, unknown>;
  status?: number;
}

export class ApiError extends Error {
  public readonly code: string;
  public readonly requestId: string | null;
  public readonly details: Record<string, unknown>;
  public readonly status?: number;

  constructor(payload: ApiErrorPayload) {
    super(payload.message || `API Error: ${payload.code}`);
    this.name = "ApiError";
    this.code = payload.code;
    this.requestId = payload.requestId;
    this.details = payload.details ?? {};
    this.status = payload.status;

    // TypeScript custom error prototype zincirini düzelt
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  toJSON(): ApiErrorPayload {
    return {
      code: this.code,
      message: this.message,
      requestId: this.requestId,
      details: this.details,
      status: this.status,
    };
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}
