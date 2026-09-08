import { useEffect, useState } from 'react';
import {
  useNavigate,
  useParams,
} from 'react-router-dom';

import {
  approveProposal,
  editProposal,
  getProposal,
  rejectProposal,
} from '../../api/proposals';

import type {
  Asset,
  AssetType,
  Proposal,
} from '../../types/api';

import { PageHeader } from '../PageHeader';

import { Button } from '../../components/Button';
import { Field } from '../../components/Field';
import { Feedback } from '../../components/Feedback';
import { Loader } from '../../components/Loader';
import { Modal } from '../../components/Modal';
import { StatusBadge } from '../../components/StatusBadge';


const textFields: Record<
  AssetType,
  string[]
> = {
  GLOSSARY: [
    'term',
    'definition',
    'synonyms',
  ],

  POLICY_RULE: [
    'rule',
    'entity_keys',
    'valid_from',
    'valid_until',
    'conditions',
  ],

  SEMANTIC_MAPPING: [
    'concept',
    'source_id',
    'database',
    'schema_name',
    'table',
    'columns',
  ],

  ENTITY: [
    'name',
    'entity_type',
    'aliases',
    'source_keys',
  ],

  RELATIONSHIP: [
    'from_entity',
    'to_entity',
    'relation_type',
  ],

  VERIFIED_SQL: [
    'source_id',
    'sql',
    'description',
    'dialect',
  ],

  AMBIGUITY: [
    'description',
    'alternatives',
    'resolution',
  ],
};


const arrayFields = new Set([
  'synonyms',
  'entity_keys',
  'columns',
  'aliases',
  'source_keys',
  'conditions',
  'alternatives',
]);


const textAreaFields = new Set([
  'definition',
  'rule',
  'sql',
  'description',
  'resolution',
]);


function displayValue(
  value: unknown,
): string {
  if (Array.isArray(value)) {
    return value.join(', ');
  }

  if (
    value === null ||
    value === undefined
  ) {
    return '';
  }

  return String(value);
}


function updateAssetField(
  asset: Asset,
  field: string,
  rawValue: string,
): Asset {
  const value = arrayFields.has(field)
    ? rawValue
        .split(',')
        .map(
          (item) => item.trim(),
        )
        .filter(Boolean)
    : rawValue;

  return {
    ...asset,
    [field]: value,
  };
}


function AssetField({
  asset,
  field,
  onChange,
}: {
  asset: Asset;
  field: string;
  onChange: (asset: Asset) => void;
}) {
  const label = field
    .replaceAll('_', ' ')
    .replace(
      /\b\w/g,
      (character) =>
        character.toUpperCase(),
    );

  const value = displayValue(
    asset[field],
  );

  if (textAreaFields.has(field)) {
    return (
      <Field label={label}>
        <textarea
          rows={
            field === 'sql'
              ? 8
              : 4
          }
          value={value}
          onChange={(event) =>
            onChange(
              updateAssetField(
                asset,
                field,
                event.target.value,
              ),
            )
          }
        />
      </Field>
    );
  }

  return (
    <Field label={label}>
      <input
        value={value}
        onChange={(event) =>
          onChange(
            updateAssetField(
              asset,
              field,
              event.target.value,
            ),
          )
        }
      />
    </Field>
  );
}


export function ProposalReviewPage() {
  const params = useParams();

  /*
   * Current route:
   *
   * /proposals/:proposalId
   *
   * Fallback to "id" so this page also works
   * if an older route definition is still present.
   */
  const proposalId =
    params.proposalId ??
    params.id;

  const navigate =
    useNavigate();

  const [
    proposal,
    setProposal,
  ] = useState<Proposal | null>(
    null,
  );

  const [
    asset,
    setAsset,
  ] = useState<Asset | null>(
    null,
  );

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    saving,
    setSaving,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState('');

  const [
    modal,
    setModal,
  ] = useState<
    'approve' | 'reject' | null
  >(null);


  /*
   * Load proposal.
   */
  useEffect(() => {
    let cancelled = false;

    async function loadProposal() {
      if (!proposalId) {
        setError(
          'Proposal ID was not provided in the URL.',
        );

        setLoading(false);

        return;
      }

      setLoading(true);
      setError('');

      try {
        const result =
          await getProposal(
            proposalId,
          );

        if (cancelled) {
          return;
        }

        setProposal(result);

        setAsset({
          ...result.reviewed_payload,
        });
      } catch (
        err: unknown
      ) {
        if (cancelled) {
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : 'Unable to load proposal.',
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadProposal();

    return () => {
      cancelled = true;
    };
  }, [proposalId]);


  /*
   * Save reviewed payload.
   */
  const save = async () => {
    if (
      !proposalId ||
      !asset
    ) {
      return;
    }

    setSaving(true);
    setError('');

    try {
      const result =
        await editProposal(
          proposalId,
          asset,
        );

      setProposal(result);

      setAsset({
        ...result.reviewed_payload,
      });
    } catch (
      err: unknown
    ) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to save changes.',
      );
    } finally {
      setSaving(false);
    }
  };


  /*
   * Approve or reject proposal.
   */
  const decide = async (
    action:
      | 'approve'
      | 'reject',
  ) => {
    if (!proposalId) {
      return;
    }

    setSaving(true);
    setError('');

    try {
      /*
       * Save any changes before the final
       * governance decision.
       */
      if (
        asset &&
        JSON.stringify(asset) !==
          JSON.stringify(
            proposal?.reviewed_payload,
          )
      ) {
        await editProposal(
          proposalId,
          asset,
        );
      }

      if (action === 'approve') {
        await approveProposal(
          proposalId,
        );
      } else {
        await rejectProposal(
          proposalId,
          'Rejected from CCE web app.',
        );
      }

      navigate('/proposals');
    } catch (
      err: unknown
    ) {
      setError(
        err instanceof Error
          ? err.message
          : `Unable to ${
              action === 'approve'
                ? 'approve'
                : 'reject'
            } proposal.`,
      );
    } finally {
      setSaving(false);
      setModal(null);
    }
  };


  /*
   * Loading state.
   */
  if (loading) {
    return (
      <section className="page">
        <Loader
          label="Loading proposal…"
        />
      </section>
    );
  }


  /*
   * Error / missing proposal.
   */
  if (
    !proposal ||
    !asset
  ) {
    return (
      <section className="page">
        <Feedback
          message={
            error ||
            'Proposal was not found.'
          }
        />

        <div
          style={{
            marginTop: 16,
          }}
        >
          <Button
            variant="secondary"
            onClick={() =>
              navigate(
                '/proposals',
              )
            }
          >
            Back to knowledge
          </Button>
        </div>
      </section>
    );
  }


  const fields =
    textFields[
      asset.asset_type
    ] ?? [];


  return (
    <section className="page">

      <PageHeader
        title="Review knowledge"
        description={`${asset.asset_type} · ${proposal.operation}`}
        action={
          <StatusBadge
            status={
              proposal.status
            }
          />
        }
      />


      {error && (
        <Feedback
          message={error}
        />
      )}


      <div className="review-layout">

        {/* Reviewed payload */}
        <div className="form-card">

          <h3>
            Reviewed payload
          </h3>

          <p className="muted">
            Edit only the reviewed
            payload. The
            machine-generated
            payload remains
            unchanged.
          </p>


          <Field label="Asset type">
            <input
              value={
                asset.asset_type
              }
              disabled
            />
          </Field>


          <Field
            label="Canonical key"
            required
          >
            <input
              value={
                asset.canonical_key
              }
              onChange={(event) =>
                setAsset({
                  ...asset,
                  canonical_key:
                    event.target.value,
                })
              }
            />
          </Field>


          {fields.map(
            (field) => (
              <AssetField
                key={field}
                asset={asset}
                field={field}
                onChange={
                  setAsset
                }
              />
            ),
          )}


          <div className="form-actions">

            <Button
              variant="secondary"
              onClick={() =>
                navigate(
                  '/proposals',
                )
              }
            >
              Back
            </Button>


            <Button
              variant="secondary"
              loading={saving}
              onClick={save}
            >
              Save changes
            </Button>


            <Button
              variant="danger"
              onClick={() =>
                setModal(
                  'reject',
                )
              }
            >
              Reject
            </Button>


            <Button
              onClick={() =>
                setModal(
                  'approve',
                )
              }
            >
              Approve
            </Button>

          </div>

        </div>


        {/* Evidence */}
        <div className="detail-card">

          <h3>
            Evidence
          </h3>


          {proposal.evidence.length ===
          0 ? (
            <p className="muted">
              No evidence attached.
            </p>
          ) : (
            <div className="evidence-list">

              {proposal.evidence.map(
                (evidence) => (
                  <div
                    className="evidence-item"
                    key={String(
                      evidence.evidence_id,
                    )}
                  >
                    <strong>
                      {
                        evidence.document_id
                      }
                    </strong>

                    <span>
                      {
                        evidence.source_uri
                      }
                    </span>
                  </div>
                ),
              )}

            </div>
          )}

        </div>

      </div>


      {/* Approve / Reject confirmation */}
      {modal && (
        <Modal
          title={
            modal === 'approve'
              ? 'Approve knowledge?'
              : 'Reject knowledge?'
          }
          confirmLabel={
            modal === 'approve'
              ? 'Approve'
              : 'Reject'
          }
          danger={
            modal === 'reject'
          }
          loading={saving}
          onClose={() =>
            setModal(null)
          }
          onConfirm={() =>
            decide(modal)
          }
        >
          <p>
            {modal ===
            'approve'
              ? 'This proposal will enter the governed package lifecycle.'
              : 'This proposal will be marked rejected and will not be served.'}
          </p>
        </Modal>
      )}

    </section>
  );
}