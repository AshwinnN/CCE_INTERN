import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { api } from './api'
import './styles.css'

const tabs = [
  { id: 'ingestion', label: 'Ingestion', icon: '↓' },
  { id: 'review', label: 'Review', icon: '✓' },
  { id: 'packages', label: 'Domain Packages', icon: '◆' },
  { id: 'questions', label: 'Ask Questions', icon: '⌁' },
]

const statusClass = (status) => `status ${String(status).toLowerCase().replaceAll('_', '-')}`

function App() {
  const [page, setPage] = useState('ingestion')
  const [packages, setPackages] = useState([])
  const [activePackageId, setActivePackageId] = useState(localStorage.getItem('cce-active-package') || '')
  const [refresh, setRefresh] = useState(0)

  const loadPackages = async () => {
    try {
      const data = await api.packages()
      setPackages(data.packages || [])
      if (!activePackageId && data.packages?.length) setActivePackageId(data.packages[0].package_id)
    } catch (error) { console.error(error) }
  }

  useEffect(() => { loadPackages() }, [refresh])
  useEffect(() => {
    if (activePackageId) localStorage.setItem('cce-active-package', activePackageId)
  }, [activePackageId])

  const activePackage = useMemo(() => packages.find(p => p.package_id === activePackageId) || packages[0], [packages, activePackageId])

  const navigate = (id) => setPage(id)

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">CCE</div>
          <div><div className="brand-title">Context Accelerator</div><div className="brand-subtitle">Governed context workspace</div></div>
        </div>
        <div className="top-status"><span className="pulse" /> Mock API · UI development mode</div>
      </header>

      <nav className="tabs" aria-label="CCE pages">
        {tabs.map(tab => (
          <button key={tab.id} className={`tab ${page === tab.id ? 'active' : ''}`} onClick={() => navigate(tab.id)}>
            <span className="tab-icon">{tab.icon}</span>{tab.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {page === 'ingestion' && <IngestionPage onComplete={() => setRefresh(v => v + 1)} />}
        {page === 'review' && <ReviewPage onChanged={() => setRefresh(v => v + 1)} />}
        {page === 'packages' && <PackagesPage packages={packages} onCreated={() => setRefresh(v => v + 1)} onActivate={setActivePackageId} activePackageId={activePackage?.package_id} />}
        {page === 'questions' && <QuestionsPage packages={packages} activePackage={activePackage} onActivate={setActivePackageId} />}
      </main>
    </div>
  )
}

function PageHeader({ eyebrow, title, description, action }) {
  return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>
}

function IngestionPage({ onComplete }) {
  const [runs, setRuns] = useState([])
  const [documentName, setDocumentName] = useState('Customer Contract - ABC.pdf')
  const [running, setRunning] = useState(false)
  const [lastRun, setLastRun] = useState(null)
  const [error, setError] = useState('')

  const load = async () => { try { setRuns((await api.ingestionRuns()).runs || []) } catch (e) { setError(e.message) } }
  useEffect(() => { load() }, [])

  const ingest = async () => {
    setRunning(true); setError('')
    try { const result = await api.ingest(documentName); setLastRun(result); await load(); onComplete() }
    catch (e) { setError(e.message) }
    finally { setRunning(false) }
  }

  return <>
    <PageHeader eyebrow="01 · SOURCE → CONTEXT" title="Ingestion" description="Start the CCE ingestion loop. The mock endpoint represents AgenticPlane Ingest, Ground, and Entity Resolution." action={<button className="primary" onClick={ingest} disabled={running}>{running ? 'Running…' : 'Run Ingestion'}</button>} />

    <section className="panel ingest-control">
      <div className="source-card"><div className="source-icon">G</div><div><strong>Customer Contract</strong><span>Google Docs · Read-only via API</span></div><span className="connected">CONNECTED</span></div>
      <label className="field"><span>Document / change event</span><input value={documentName} onChange={e => setDocumentName(e.target.value)} /></label>
      <div className="pipeline">
        <Stage title="Ingest" text="Chunk · classify · embed" done={lastRun?.agentic_plane?.ingest} />
        <div className="connector" />
        <Stage title="Ground" text="Source references · DLP" done={lastRun?.agentic_plane?.ground} />
        <div className="connector" />
        <Stage title="Entity Resolution" text="Contract ↔ Snowflake graph" done={lastRun?.agentic_plane?.entity_resolution} />
      </div>
      {lastRun && <div className="run-result"><div><b>Ingestion completed</b><span>Trace {lastRun.trace_id}</span></div><div className="metrics"><Metric value={lastRun.chunks} label="chunks"/><Metric value={lastRun.grounded_facts} label="grounded facts"/><Metric value={lastRun.resolved_entities} label="entities resolved"/></div></div>}
      {error && <div className="error">{error}</div>}
    </section>

    <div className="section-title"><div><h2>Ingestion Runs</h2><span>New or changed files re-enter the active context loop.</span></div></div>
    <section className="table-panel"><table><thead><tr><th>Run</th><th>Source</th><th>Stage</th><th>Objects</th><th>Trace</th><th>Status</th></tr></thead><tbody>{runs.map(run => <tr key={run.run_id}><td><b>{run.run_id}</b><small>{run.document_name}</small></td><td>{run.source}</td><td>{run.stage.replaceAll('_', ' ')}</td><td>{run.objects_processed}</td><td className="mono">{run.trace_id}</td><td><span className={statusClass(run.status)}>{run.status}</span></td></tr>)}</tbody></table></section>
  </>
}

function Stage({ title, text, done }) { return <div className={`stage ${done ? 'done' : ''}`}><div className="stage-dot">{done ? '✓' : '○'}</div><div><b>{title}</b><span>{text}</span></div></div> }
function Metric({ value, label }) { return <div><b>{value}</b><span>{label}</span></div> }

function ReviewPage({ onChanged }) {
  const [proposals, setProposals] = useState([])
  const [selected, setSelected] = useState(null)
  const [comment, setComment] = useState('')
  const [filter, setFilter] = useState('PROPOSED')
  const [error, setError] = useState('')

  const load = async () => { try { setProposals((await api.proposals()).proposals || []) } catch (e) { setError(e.message) } }
  useEffect(() => { load() }, [])

  const decide = async (decision) => {
    if (!selected) return
    try { if (decision === 'APPROVED') await api.approve(selected.proposal_id, comment); else await api.reject(selected.proposal_id, comment); setSelected(null); setComment(''); await load(); onChanged() }
    catch (e) { setError(e.message) }
  }
  const visible = proposals.filter(p => filter === 'ALL' || p.status === filter)

  return <>
    <PageHeader eyebrow="02 · HUMAN GOVERNANCE" title="Review Proposals" description="Everything enters as PROPOSED. The Domain Steward reviews evidence before anything becomes usable context." />
    <div className="filter-row">{['PROPOSED', 'APPROVED', 'REJECTED', 'ALL'].map(x => <button key={x} className={`filter ${filter === x ? 'selected' : ''}`} onClick={() => setFilter(x)}>{x} <span>{proposals.filter(p => x === 'ALL' || p.status === x).length}</span></button>)}</div>
    {error && <div className="error">{error}</div>}
    <div className="review-grid">
      <section className="panel proposal-list">{visible.map(p => <button key={p.proposal_id} className={`proposal-row ${selected?.proposal_id === p.proposal_id ? 'selected' : ''}`} onClick={() => setSelected(p)}><div className="proposal-type">{p.type.replaceAll('_', ' ')}</div><div className="proposal-main"><b>{p.title}</b><span>{p.candidate}</span></div><div className="proposal-confidence">{Math.round(p.confidence * 100)}%</div><span className={statusClass(p.status)}>{p.status}</span></button>)}{visible.length === 0 && <Empty text="No proposals in this state."/>}</section>
      <section className="panel proposal-detail">{selected ? <><div className="detail-head"><div><div className="eyebrow">{selected.type.replaceAll('_', ' ')}</div><h2>{selected.title}</h2></div><span className={statusClass(selected.status)}>{selected.status}</span></div><div className="candidate"><span>Machine candidate</span><p>{selected.candidate}</p></div><h3>Evidence</h3><div className="evidence-list">{selected.evidence.map((e, i) => <div className="evidence" key={i}><div className="evidence-source">{e.source}<span>{e.location}</span></div><p>{e.snippet}</p></div>)}</div><div className="review-actions">{selected.status === 'PROPOSED' ? <><textarea value={comment} onChange={e => setComment(e.target.value)} placeholder="Optional review comment…"/><div><button className="danger" onClick={() => decide('REJECTED')}>Reject</button><button className="primary" onClick={() => decide('APPROVED')}>Approve</button></div></> : <div className="reviewed">Reviewed by {selected.review?.approved_by || 'Domain Steward'} · {selected.review?.reviewed_at || 'mock review'}</div>}</div></> : <Empty text="Select a proposal to review its evidence."/>}</section>
    </div>
  </>
}

function PackagesPage({ packages, onCreated, onActivate, activePackageId }) {
  const [approved, setApproved] = useState([])
  const [name, setName] = useState('Delivery Performance')
  const [description, setDescription] = useState('Governed context for delivery SLA questions.')
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => { api.proposals('APPROVED').then(d => setApproved(d.proposals || [])).catch(() => {}) }, [onCreated])

  const create = async () => {
    setCreating(true); setMessage('')
    try { const p = await api.createPackage({ name, description, proposal_ids: approved.map(p => p.proposal_id) }); onActivate(p.package_id); setMessage(`Created ${p.name} ${p.active_version}`); onCreated() }
    catch (e) { setMessage(e.message) } finally { setCreating(false) }
  }

  return <>
    <PageHeader eyebrow="03 · GOVERNED CONTEXT" title="Domain Packages" description="Build a reusable governed object containing glossary, semantic model, policy rules, verified SQL, entity graph, and ambiguity state." />
    <div className="package-layout">
      <section><div className="section-title"><div><h2>Packages</h2><span>Choose the package served to the question workspace.</span></div></div><div className="package-list">{packages.map(p => <div className={`package-card ${p.package_id === activePackageId ? 'active' : ''}`} key={p.package_id}><div className="package-card-head"><div><b>{p.name}</b><span>{p.description}</span></div>{p.package_id === activePackageId ? <span className="active-pill">ACTIVE SELECTION</span> : <button className="ghost" onClick={() => onActivate(p.package_id)}>Use package</button>}</div><div className="package-meta"><span>Version <b>{p.active_version}</b></span><span>{p.assets.length} assets</span><span>Approved by {p.approved_by}</span><span>Valid until {p.valid_until}</span></div><div className="asset-chips">{p.assets.map(a => <span key={a}>{a}</span>)}</div></div>)}{packages.length === 0 && <Empty text="No domain packages yet."/>}</div></section>
      <section className="panel create-package"><div className="eyebrow">PACKAGE BUILDER</div><h2>Create Domain Package</h2><p>Only approved proposals are eligible. This mock builder creates v1.0 and marks it active.</p><label className="field"><span>Name</span><input value={name} onChange={e => setName(e.target.value)} /></label><label className="field"><span>Description</span><textarea value={description} onChange={e => setDescription(e.target.value)} /></label><div className="selected-assets"><div><b>Approved assets</b><span>{approved.length} selected</span></div>{approved.map(p => <div className="selected-asset" key={p.proposal_id}><span>✓</span>{p.title}</div>)}{approved.length === 0 && <div className="hint">Approve proposals in Review first.</div>}</div><button className="primary full" disabled={!approved.length || creating} onClick={create}>{creating ? 'Creating…' : 'Create & Activate Package'}</button>{message && <div className="success-message">{message}</div>}</section>
    </div>
  </>
}

function QuestionsPage({ packages, activePackage, onActivate }) {
  const [question, setQuestion] = useState('Is Customer ABC currently meeting its delivery SLA? Which SLA applies, and why?')
  const [contextOn, setContextOn] = useState(true)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const ask = async () => {
    if (!activePackage) return
    setLoading(true); setError('')
    try { setResult(await api.compare({ question, package_id: activePackage.package_id, context_enabled: contextOn })) }
    catch (e) { setError(e.message) } finally { setLoading(false) }
  }

  return <>
    <PageHeader eyebrow="04 · RUNTIME PROOF" title="Ask Questions" description="Compare Context OFF and Context ON side by side. ON is the governed answer shown by default." action={<div className="package-select"><span>Active package</span><select value={activePackage?.package_id || ''} onChange={e => onActivate(e.target.value)}>{packages.map(p => <option key={p.package_id} value={p.package_id}>{p.name} · {p.active_version}</option>)}</select></div>} />
    <section className="panel question-box"><textarea value={question} onChange={e => setQuestion(e.target.value)} /><div className="question-toolbar"><div className="toggle"><button className={contextOn ? 'on' : ''} onClick={() => setContextOn(true)}>Context ON</button><button className={!contextOn ? 'off' : ''} onClick={() => setContextOn(false)}>Context OFF</button></div><button className="primary" onClick={ask} disabled={loading || !activePackage}>{loading ? 'Resolving…' : 'Ask CCE'}</button></div></section>
    {error && <div className="error">{error}</div>}
    {result && <><div className="compare-grid"><AnswerCard title="Context OFF" tone="off" data={result.context_off}/><AnswerCard title="Context ON" tone="on" data={result.context_on}/></div><section className="panel trace-panel"><div className="trace-title"><div><div className="eyebrow">TRACEABILITY & OBSERVABILITY</div><h2>Why Context ON answered differently</h2></div><span className="trace-id">{result.context_on.trace_id}</span></div><div className="trace-grid"><div><span>Package</span><b>{result.context_on.package_id} · {result.context_on.package_version}</b></div><div><span>Applied rule</span><b>{result.context_on.applied_rule}</b></div><div><span>Approved by</span><b>{result.context_on.approver}</b></div><div><span>Valid until</span><b>{result.context_on.valid_until}</b></div></div><div className="sql"><span>Verified SQL</span><code>{result.context_on.executed_sql}</code></div><div className="citations"><span>Evidence</span>{result.context_on.citations.map((c, i) => <div key={i}><b>{c.source}</b><span>{c.location}</span><p>{c.detail}</p></div>)}</div></section></>}
    {!result && <div className="proof-hint"><b>The MVP proof</b><span>82% vs standard 90% → NO</span><span>82% vs approved 80% → YES</span><small>Run the question to see the governed comparison and trace.</small></div>}
  </>
}

function AnswerCard({ title, tone, data }) { return <section className={`answer-card ${tone}`}><div className="answer-head"><div><span>{title}</span><h2>{data.answer}</h2></div><span className="answer-badge">{data.context_used ? 'Governed' : 'Baseline'}</span></div><div className="comparison"><span>Comparison</span><b>{data.comparison}</b></div><p>{data.rationale}</p><div className="answer-foot"><span>Confidence <b>{Math.round(data.confidence * 100)}%</b></span>{data.package_version && <span>Package <b>{data.package_version}</b></span>}</div></section> }
function Empty({ text }) { return <div className="empty">{text}</div> }

createRoot(document.getElementById('root')).render(<App />)
