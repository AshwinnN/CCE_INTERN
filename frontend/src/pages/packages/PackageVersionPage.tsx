import {
  useEffect,
  useState,
} from 'react';

import {
  Link,
  useParams,
} from 'react-router-dom';

import {
  getPackageVersion,
} from '../../api/packages';

import type {
  PackageSnapshot,
} from '../../types/api';

import { PageHeader } from '../PageHeader';
import { Loader } from '../../components/Loader';
import { Feedback } from '../../components/Feedback';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/Button';

export function PackageVersionPage() {
  const {
    packageId,
    version,
  } = useParams();

  const [snapshot, setSnapshot] =
    useState<PackageSnapshot | null>(
      null,
    );

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState('');

  useEffect(() => {
    if (!packageId || !version) {
      setError(
        'Package ID or version is missing from the URL.',
      );
      setLoading(false);
      return;
    }

    let cancelled = false;

    getPackageVersion(
      packageId,
      version,
    )
      .then((result) => {
        if (!cancelled) {
          setSnapshot(result);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Unable to load package version.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    packageId,
    version,
  ]);

  if (loading) {
    return (
      <section className="page">
        <Loader
          label="Loading package version…"
        />
      </section>
    );
  }

  if (!snapshot) {
    return (
      <section className="page">
        <Feedback
          message={
            error ||
            'Package version not found.'
          }
        />
      </section>
    );
  }

  return (
    <section className="page">

      <PageHeader
        title={`Package version ${snapshot.version}`}
        description={snapshot.package_id}
        action={
          <Link
            to={`/packages/${snapshot.package_id}`}
          >
            <Button variant="secondary">
              Back to package
            </Button>
          </Link>
        }
      />

      <div className="detail-card">

        <div className="status-line">
          <span>Status</span>

          <StatusBadge
            status={snapshot.status}
          />

          <span>
            Assets: {snapshot.assets.length}
          </span>
        </div>

      </div>

      <div className="asset-grid">

        {snapshot.assets.map(
          (asset) => (
            <article
              className="asset-card"
              key={String(
                asset.asset_id,
              )}
            >
              <div className="asset-top">
                <span className="asset-type">
                  {
                    asset.payload
                      .asset_type
                  }
                </span>

                <span>
                  Revision{' '}
                  {asset.revision_no}
                </span>
              </div>

              <h3>
                {
                  asset.payload
                    .canonical_key
                }
              </h3>

              <pre className="json-view">
                {JSON.stringify(
                  asset.payload,
                  null,
                  2,
                )}
              </pre>

              {asset.approved_by && (
                <small>
                  Approved by{' '}
                  {asset.approved_by}
                </small>
              )}
            </article>
          ),
        )}

      </div>
    </section>
  );
}