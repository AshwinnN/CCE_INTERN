import { apiRequest } from './client';

import type {
  IngestionRun,
  Source,
  SourceOperationResult,
} from '../types/api';

export function listSources(): Promise<Source[]> {
  return apiRequest<Source[]>(
    '/sources',
  );
}

export function createSource(
  body: {
    adapter: string;
    source_id: string;
    credential_ref: string;
    kind: string;
    config: Record<string, unknown>;
  },
): Promise<Source> {
  return apiRequest<Source>(
    '/sources',
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

export function testSource(
  sourceId: string,
): Promise<SourceOperationResult> {
  return apiRequest<SourceOperationResult>(
    `/sources/${encodeURIComponent(sourceId)}/test`,
    {
      method: 'POST',
    },
  );
}

export function startIngestion(
  sourceId: string,
): Promise<IngestionRun> {
  return apiRequest<IngestionRun>(
    `/sources/${encodeURIComponent(sourceId)}/ingest`,
    {
      method: 'POST',
    },
  );
}

export function getIngestionRun(
  runId: string,
): Promise<IngestionRun> {
  return apiRequest<IngestionRun>(
    `/ingestion-runs/${encodeURIComponent(runId)}`,
  );
}