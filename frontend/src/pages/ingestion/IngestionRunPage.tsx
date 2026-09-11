import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { getIngestionRun } from '../../api/sources';
import type { IngestionRun } from '../../types/api';
import { Button } from '../../components/Button';
import { Feedback } from '../../components/Feedback';
import { Loader } from '../../components/Loader';
import { StatusBadge } from '../../components/StatusBadge';
import { PageHeader } from '../PageHeader';

const terminal = new Set(['COMPLETE', 'FAILED', 'CANCELLED', 'PARTIAL', 'ERROR']);

export function IngestionRunPage() {
  const { runId } = useParams();
  const [run, setRun] = useState<IngestionRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async (manual = false) => {
    if (!runId) return;
    if (manual) setRefreshing(true);
    try {
      const result = await getIngestionRun(runId);
      setRun(result);
      setError('');
      if (!terminal.has(result.status)) {
        timer.current = window.setTimeout(() => load(false), 3000);
      }
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
      if (manual) setRefreshing(false);
    }
  }, [runId]);

  useEffect(() => {
    load(false);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [load]);

  if (loading) return <section className="page"><Loader label="Checking ingestion status…" /></section>;

  return <section className="page">
    <PageHeader title="Ingestion run" description={runId} action={<Button variant="secondary" loading={refreshing} onClick={() => load(true)}>Refresh</Button>} />
    {error && <Feedback message={error} />}
    <div className="detail-card ingestion-card">
      <div className="status-line"><span>Status</span><StatusBadge status={run?.status || 'UNKNOWN'} />{run && !terminal.has(run.status) && <span className="live-note"><span className="pulse" /> Auto-refreshing</span>}</div>
      {run && !terminal.has(run.status) && <Loader label="Waiting for the next status update…" />}
      {run?.error && <Feedback message={run.error.message} />}
      <div className="metrics"><div><span>Objects processed</span><strong>{run?.objects_processed ?? 0}</strong></div><div><span>Objects failed</span><strong>{run?.objects_failed ?? 0}</strong></div></div>
      {run?.status === 'COMPLETE' && <div className="next-step"><p>Ingestion completed. Knowledge proposals can now be reviewed when available.</p><Link to="/proposals"><Button>Open Knowledge</Button></Link></div>}
    </div>
  </section>;
}
