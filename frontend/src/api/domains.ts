import {
  api,
  post,
} from './client';

import type {
  Domain,
} from '../types/api';

import {
  appConfig,
} from '../config/app';

export function listDomains() {
  return api<Domain[]>(
    '/domains',
  );
}

export function createDomain(
  body: Omit<
    Domain,
    | 'domain_id'
    | 'enabled'
    | 'has_active_package'
  >,
) {
  return post<Domain>(
    '/domains',
    {
      ...body,

      actor: {
        actor_id:
          appConfig.actorId,

        roles:
          appConfig.actorRoles,
      },
    },
  );
}