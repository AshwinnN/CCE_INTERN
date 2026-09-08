import {
  useEffect,
  useState,
} from 'react';

import {
  Link,
  useParams,
} from 'react-router-dom';

import {
  getActivePackage,
  getPackage,
} from '../../api/packages';

import type {
  PackageInfo,
  PackageSnapshot,
} from '../../types/api';

import { PageHeader } from '../PageHeader';
import { Loader } from '../../components/Loader';
import { Feedback } from '../../components/Feedback';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/Button';

export function PackageDetailsPage() {
  const { packageId } =
    useParams();

  const [pkg, setPkg] =
    useState<PackageInfo | null>(
      null,
    );

  const [snapshot, setSnapshot] =
    useState<PackageSnapshot | null>(
      null,
    );

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState('');

  useEffect(() => {
    if (!packageId) {
      setError(
        'Package ID is missing from the URL.',
      );
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        const result =
          await getPackage(
            packageId,
          );

        if (cancelled) {
          return;
        }

        setPkg(result);

        const active =
          await getActivePackage(
            result.domain_id,
          );

        if (!cancelled) {
          setSnapshot(active);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Unable to load package.',
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [packageId]);

  if (loading) {
    return (
      <section className="page">
        <Loader
          label="Loading package…"
        />
      </section>
    );
  }

  if (!pkg) {
    return (
      <section className="page">
        <Feedback
          message={
            error ||
            'Package not found.'
          }
        />
      </section>
    );
  }

  return (
    <section className="page">

      <PageHeader
        title={pkg.name}
        description="Package details"
        action={
          <Link to="/packages">
            <Button variant="secondary">
              Back to packages
            </Button>
          </Link>
        }
      />

      {error && (
        <Feedback
          message={error}
        />
      )}

      <div className="detail-grid">

        <div className="detail-card">
          <h3>Package</h3>

          <dl>
            <dt>Package ID</dt>
            <dd className="mono">
              {pkg.package_id}
            </dd>

            <dt>Domain ID</dt>
            <dd className="mono">
              {pkg.domain_id}
            </dd>

            {snapshot && (
              <>
                <dt>Active version</dt>
                <dd>
                  {snapshot.version}
                </dd>

                <dt>Status</dt>
                <dd>
                  <StatusBadge
                    status={
                      snapshot.status
                    }
                  />
                </dd>
              </>
            )}
          </dl>
        </div>

        <div className="detail-card">
          <h3>
            Active version
          </h3>

          {snapshot ? (
            <>
              <p>
                {snapshot.assets.length}{' '}
                governed assets.
              </p>

              <Link
                to={`/packages/${pkg.package_id}/versions/${snapshot.version}`}
              >
                <Button>
                  View version
                </Button>
              </Link>
            </>
          ) : (
            <p className="muted">
              No active package snapshot
              is available for this
              domain.
            </p>
          )}
        </div>

      </div>
    </section>
  );
}