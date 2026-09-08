import {
  api,
  patch,
  post,
} from './client';

import type {
  Proposal,
} from '../types/api';

import {
  appConfig,
} from '../config/app';

const actor = {
  actor_id: appConfig.actorId,
  roles: appConfig.actorRoles,
};

export function listProposals(
  status?: string,
) {
  const query =
    status
      ? `?status=${encodeURIComponent(status)}`
      : '';

  return api<{
    proposals: Proposal[];
  }>(
    `/proposals${query}`,
  );
}

export function getProposal(
  proposalId: string,
) {
  return api<Proposal>(
    `/proposals/${encodeURIComponent(proposalId)}`,
  );
}

export function editProposal(
  proposalId: string,
  payload: Record<string, any>,
  comment = '',
) {
  return patch<Proposal>(
    `/proposals/${encodeURIComponent(proposalId)}`,
    {
      actor,
      payload,
      comment,
    },
  );
}

export function approveProposal(
  proposalId: string,
  comment = '',
) {
  return post<Proposal>(
    `/proposals/${encodeURIComponent(proposalId)}/approve`,
    {
      actor,
      comment,
    },
  );
}

export function rejectProposal(
  proposalId: string,
  reason = '',
) {
  return post<Proposal>(
    `/proposals/${encodeURIComponent(proposalId)}/reject`,
    {
      actor,
      reason,
    },
  );
}