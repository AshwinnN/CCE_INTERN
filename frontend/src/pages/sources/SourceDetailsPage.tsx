import {
  useEffect,
  useState,
} from 'react';

import {
  Link,
  useNavigate,
  useParams,
} from 'react-router-dom';

import {
  listSources,
  startIngestion,
  testSource,
} from '../../api/sources';

import type {
  IngestionRun,
  Source,
} from '../../types/api';

import { PageHeader } from '../PageHeader';

import { Button } from '../../components/Button';
import { Feedback } from '../../components/Feedback';
import { Loader } from '../../components/Loader';
import { StatusBadge } from '../../components/StatusBadge';

export function SourceDetailsPage() {
  const params = useParams();

  /*
   * Primary route:
   *
   * /sources/:sourceId
   *
   * The second fallback also makes this component
   * tolerant of an older /sources/:id route.
   */
  const sourceId =
    params.sourceId ??
    params.id;

  const navigate = useNavigate();

  const [source, setSource] =
    useState<Source | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [busy, setBusy] =
    useState<
      'test' | 'ingest' | ''
    >('');

  const [error, setError] =
    useState('');

  const [success, setSuccess] =
    useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadSource() {
      if (!sourceId) {
        setError(
          'Source ID was not provided in the URL.',
        );
        setLoading(false);
        return;
      }

      setLoading(true);
      setError('');

      try {
        const sources =
          await listSources();

        if (cancelled) {
          return;
        }

        const selected =
          sources.find(
            (item) =>
              String(item.source_id) ===
              String(sourceId),
          );

        if (!selected) {
          setSource(null);

          setError(
            `Source "${sourceId}" was not found in the sources returned by the API.`,
          );

          return;
        }

        setSource(selected);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Unable to load source.',
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadSource();

    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  async function test() {
    if (!sourceId) {
      setError(
        'Source ID is missing.',
      );
      return;
    }

    setBusy('test');
    setError('');
    setSuccess('');

    try {
      const result =
        await testSource(
          sourceId,
        );

      if (result.error) {
        throw new Error(
          result.error.message ||
          'Connection test failed.',
        );
      }

      setSuccess(
        `Connection test completed: ${result.status}.`,
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Connection test failed.',
      );
    } finally {
      setBusy('');
    }
  }

  async function ingest() {
    if (!sourceId) {
      setError(
        'Source ID is missing.',
      );
      return;
    }

    setBusy('ingest');
    setError('');
    setSuccess('');

    try {
      const result: IngestionRun =
        await startIngestion(
          sourceId,
        );

      navigate(
        `/ingestion-runs/${result.ingestion_run_id}`,
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to start ingestion.',
      );

      setBusy('');
    }
  }

  if (loading) {
    return (
      <section className="page">
        <Loader
          label="Loading source…"
        />
      </section>
    );
  }

  if (!source) {
    return (
      <section className="page">
        <Feedback
          message={
            error ||
            'Source was not found.'
          }
        />

        <div
          style={{
            marginTop: 16,
          }}
        >
          <Link to="/sources">
            Back to sources
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="page">

      <PageHeader
        title={source.source_id}
        description={`${source.adapter} source`}
        action={
          <Link to="/sources">
            <Button variant="secondary">
              Back to sources
            </Button>
          </Link>
        }
      />

      {error && (
        <Feedback
          message={error}
        />
      )}

      {success && (
        <Feedback
          message={success}
          type="success"
        />
      )}

      <div className="detail-grid">

        <div className="detail-card">
          <h3>Connection</h3>

          <dl>
            <dt>Adapter</dt>
            <dd>
              {source.adapter}
            </dd>

            <dt>Kind</dt>
            <dd>
              {source.kind || '—'}
            </dd>

            <dt>Credential reference</dt>
            <dd>
              {source.credential_ref || '—'}
            </dd>

            <dt>Status</dt>
            <dd>
              <StatusBadge
                status={
                  source.enabled === false
                    ? 'DISABLED'
                    : 'ENABLED'
                }
              />
            </dd>
          </dl>
        </div>

        <div className="detail-card">
          <h3>Actions</h3>

          <p className="muted">
            Test the source first,
            then start ingestion.
          </p>

          <div className="button-row">

            <Button
              variant="secondary"
              loading={
                busy === 'test'
              }
              onClick={test}
            >
              Test connection
            </Button>

            <Button
              loading={
                busy === 'ingest'
              }
              onClick={ingest}
            >
              Start ingestion
            </Button>

          </div>
        </div>

      </div>

      <div className="detail-card">
        <h3>
          Configuration
        </h3>

        <pre className="json-view">
          {JSON.stringify(
            source.config,
            null,
            2,
          )}
        </pre>
      </div>

    </section>
  );
}