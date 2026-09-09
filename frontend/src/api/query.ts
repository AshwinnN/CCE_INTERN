import { post } from './client';

import type {
  QueryResponse,
} from '../types/api';

import {
  appConfig,
} from '../config/app';

export function runQuery(
  question: string,
  domainId?: string,
  contextEnabled = true,
) {
  return post<QueryResponse>(
    '/query',
    {
      question,

      domain_id:
        domainId || null,

      context_enabled:
        contextEnabled,

      actor: {
        actor_id:
          appConfig.actorId,

        roles:
          appConfig.actorRoles,
      },
    },
    {
      timeoutMs: appConfig.queryTimeoutMs,
    },
  );
}
