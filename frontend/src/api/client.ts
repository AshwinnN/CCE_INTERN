import { appConfig } from '../config/app';

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(
    `${appConfig.apiBaseUrl}${path}`,
    {
      ...options,

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
): Promise<T> {
  return apiRequest<T>(
    path,
    {
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