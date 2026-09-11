import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';

import { listDomains } from '../../api/domains';
import { runQuery } from '../../api/query';
import type { Domain, QueryBranch, QueryResponse } from '../../types/api';
import { Button } from '../../components/Button';
import { Feedback } from '../../components/Feedback';
import { Field } from '../../components/Field';
import { Loader } from '../../components/Loader';
import { StatusBadge } from '../../components/StatusBadge';
import { PageHeader } from '../PageHeader';
import '../../styles/query.css';

function detailLabel(value: unknown, fallback: string) {
  if (!value || typeof value !== 'object') return fallback;
  const detail = value as Record<string, unknown>;
  return String(detail.source_uri || detail.source_id || detail.memory_id || detail.asset_id || fallback);
}

function Details({ title, values }: { title: string; values: unknown[] }) {
  if (!values?.length) return null;
  return <><span className="section-label">{title}</span><div className="response-details">
    {values.map((value, index) => <details key={index}><summary>{detailLabel(value, `${title} ${index + 1}`)}</summary><pre className="json-view">{JSON.stringify(value, null, 2)}</pre></details>)}
  </div></>;
}

function Branch({ title, branch, contextOff = false }: { title: string; branch: QueryBranch; contextOff?: boolean }) {
  return <div className="branch-card">
    <div className="branch-head"><h3 className={contextOff ? 'context-off-title' : undefined}>{title}</h3><StatusBadge status={branch.status} /></div>
    {branch.answer && <><span className="section-label">Answer</span><div className="answer">{branch.answer}</div></>}
    {branch.sql && <><span className="section-label">SQL</span><pre className="sql-view">{branch.sql}</pre></>}
    {branch.rows?.length > 0 && <><span className="section-label">Rows</span><div className="table-card compact"><table><thead><tr>{Object.keys(branch.rows[0]).map((key) => <th key={key}>{key}</th>)}</tr></thead><tbody>{branch.rows.slice(0, 20).map((row, index) => <tr key={index}>{Object.keys(branch.rows[0]).map((key) => <td key={key}>{String(row[key] ?? '')}</td>)}</tr>)}</tbody></table></div></>}
    <Details title="Citations" values={branch.citations} />
    <Details title="Context used" values={branch.context_used} />
    <Details title="SQL attempts" values={branch.sql_attempts} />
    {branch.warnings?.length > 0 && <div className="warning-box">{branch.warnings.map((warning, index) => <div key={index}>{warning}</div>)}</div>}
    {branch.message && <p className="muted">{branch.message}</p>}
  </div>;
}

function QueryResponseView({ response }: { response: QueryResponse }) {
  return <div className="query-results">
    <PageHeader title="Latest query result" description={response.question} />
    <div className="proof-banner"><div><span>Proof classification</span><strong>{response.proof.classification.replaceAll('_', ' ')}</strong></div><p>{response.proof.explanation}</p></div>
    <div className="runtime-meta"><div><span>Trace</span><code>{response.trace_id}</code></div><div><span>Domain</span><strong>{response.domain.name || 'Unresolved'}</strong></div><div><span>Package</span><strong>{response.package.version ? `v${response.package.version}` : response.package.status}</strong></div></div>
    <div className="branch-grid"><Branch title="Context ON" branch={response.context_on} /><Branch title="Context OFF" branch={response.context_off} contextOff /></div>
    {response.errors.length > 0 && <div className="detail-card"><h3>Workflow issues</h3>{response.errors.map((item, index) => <p key={index}><b>{item.node}</b>: {item.message}</p>)}</div>}
  </div>;
}

export function QueryPage() {
  const [question, setQuestion] = useState('');
  const [domain, setDomain] = useState('');
  const [context, setContext] = useState(true);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [response, setResponse] = useState<QueryResponse | null>(null);

  useEffect(() => { listDomains().then(setDomains).catch(() => {}); }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) { setError('Question is required.'); return; }
    setError('');
    setLoading(true);
    try {
      setResponse(await runQuery(question.trim(), domain || undefined, context));
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return <section className="page narrow">
    <PageHeader title="Query" description="Run a governed question through the CCE runtime and compare Context ON vs Context OFF." />
    <div className="form-card"><form onSubmit={submit}>
      {error && <Feedback message={error} />}
      <Field label="Question" required hint="Maximum 16,000 characters."><textarea rows={7} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a business question…" /></Field>
      <Field label="Domain"><select value={domain} onChange={(event) => setDomain(event.target.value)}><option value="">Let CCE resolve the domain</option>{domains.filter((item) => item.enabled).map((item) => <option key={item.domain_id} value={item.domain_id}>{item.name}</option>)}</select></Field>
      <label className="switch-row"><input type="checkbox" checked={context} onChange={(event) => setContext(event.target.checked)} /><span>Context enabled</span></label>
      <div className="form-actions"><Button type="submit" loading={loading}>Run query</Button></div>
    </form></div>
    {loading && <Loader label="Running governed query…" />}
    {response && <QueryResponseView response={response} />}
  </section>;
}
