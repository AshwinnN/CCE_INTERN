import { appConfig } from '../config/app';

type ApiRequestOptions = RequestInit & {
  timeoutMs?: number;
};

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { timeoutMs, signal: callerSignal, ...requestOptions } = options;
  const controller = new AbortController();
  let timedOut = false;
  const timeout = timeoutMs
    ? window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs)
    : undefined;

  const abortFromCaller = () => controller.abort();
  callerSignal?.addEventListener('abort', abortFromCaller, { once: true });

  try {
    const response = await fetch(
      `${appConfig.apiBaseUrl}${path}`,
      {
        ...requestOptions,
        signal: controller.signal,

        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
      },
    );

    let body: unknown = null;

    try {
      body = await response.json();
    } catch {
      // Response does not contain JSON.
    }

    if (!response.ok) {
      let message =
        `Request failed with status ${response.status}.`;

      if (
        typeof body === 'object' &&
        body !== null &&
        'detail' in body
      ) {
        const detail = (
          body as { detail?: unknown }
        ).detail;

        if (typeof detail === 'string') {
          message = detail;
        } else if (detail !== undefined) {
          message = JSON.stringify(detail);
        }
      }

      throw new Error(message);
    }

    return body as T;
  } catch (error) {
    if (timedOut) {
      throw new Error(
        'The request timed out. The query may still be processing on the server; please check the backend logs and try again.',
      );
    }

    throw error;
  } finally {
    if (timeout !== undefined) {
      window.clearTimeout(timeout);
    }
    callerSignal?.removeEventListener('abort', abortFromCaller);
  }
}

/*
 * Generic GET helper.
 */
export function api<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  return apiRequest<T>(
    path,
    options,
  );
}

/*
 * Generic POST helper.
 */
export function post<T>(
  path: string,
  body?: unknown,
  options?: ApiRequestOptions,
): Promise<T> {
  return apiRequest<T>(
    path,
    {
      ...options,
      method: 'POST',
      body:
        body === undefined
          ? undefined
          : JSON.stringify(body),
    },
  );
}

/*
 * Generic PATCH helper.
 */
export function patch<T>(
  path: string,
  body?: unknown,
): Promise<T> {
  return apiRequest<T>(
    path,
    {
      method: 'PATCH',
      body:
        body === undefined
          ? undefined
          : JSON.stringify(body),
    },
  );
}
