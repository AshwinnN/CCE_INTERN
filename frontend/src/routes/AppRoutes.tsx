import {useEffect,useState} from 'react';
import type {FormEvent,ReactNode} from 'react';
import {Routes,Route,Link,NavLink,Navigate,useNavigate,useParams} from 'react-router-dom';
import {apiRequest} from '../api/client';
import {appConfig} from '../config/app';

type Obj=Record<string,any>;
const actor={actor_id:appConfig.actorId,roles:appConfig.actorRoles};
const request=(path:string,method='GET',payload?:Obj)=>apiRequest<any>(path,{method,body:method==='GET'?undefined:JSON.stringify({...payload,actor})});
const scope=(id:string)=>'/workspaces/'+encodeURIComponent(id);

function useLoad(path:string){
  const[data,setData]=useState<any>(null),[error,setError]=useState('');
  const reload=()=>request(path).then(setData).catch(e=>setError(e.message));
  useEffect(()=>{setData(null);setError('');reload()},[path]);
  return{data,error,reload};
}

function ErrorBox({message}:{message:string}){
  return message?<div className="feedback feedback-error" role="alert">{message}</div>:null;
}

function SuccessBox({message}:{message:string}){
  return message?<div className="feedback feedback-success" role="status">{message}</div>:null;
}

function Loader(){
  return <div className="loader-wrap"><span className="spinner"/>Loading...</div>;
}

function EmptyState({title,hint}:{title:string,hint?:string}){
  return <div className="empty-state"><h3>{title}</h3>{hint&&<p>{hint}</p>}</div>;
}

const TABS=['sources','proposals','package','query'];

function Shell({title,actions,children}:{title?:string,actions?:ReactNode,children:ReactNode}){
  const{workspaceId}=useParams();
  return <div className="app-shell">
    <header className="header"><div className="header-inner">
      <Link to="/workspaces" className="brand">
        <span className="brand-mark">CCE</span>
        <span className="brand-word">CoStrategix Context Engine</span>
      </Link>
      {workspaceId&&<nav className="nav">{TABS.map(p=>
        <NavLink key={p} to={scope(workspaceId)+'/'+p} className={({isActive}:{isActive:boolean})=>'nav-link'+(isActive?' active':'')}>
          {p.charAt(0).toUpperCase()+p.slice(1)}
        </NavLink>
      )}</nav>}
    </div></header>
    <main className="main"><div className="page">
      {title&&<div className="page-header"><h1>{title}</h1>{actions}</div>}
      {children}
    </div></main>
  </div>;
}

function Landing(){
  const{data,error}=useLoad('/workspaces');
  if(error)return <div className="login-shell"><ErrorBox message={error}/></div>;
  if(!data)return <div className="login-shell"><Loader/></div>;
  return <Navigate replace to={data.length?'/workspaces':'/workspaces/new'}/>;
}

function Workspaces(){
  const{data,error,reload}=useLoad('/workspaces');
  const[issue,setIssue]=useState('');
  async function change(w:Obj,archive=false){
    try{
      if(archive){
        if(!confirm('Archive this workspace? Its history will be retained.'))return;
        await request(scope(w.workspace_id),'DELETE');
      }else{
        const name=prompt('Workspace name',w.name);
        if(!name)return;
        await request(scope(w.workspace_id),'PATCH',{name});
      }
      reload();
    }catch(e:any){setIssue(e.message)}
  }
  return <Shell title="Workspaces" actions={<Link className="btn btn-primary" to="/workspaces/new">Create workspace</Link>}>
    <ErrorBox message={error||issue}/>
    {!data?<Loader/>:!data.length?<EmptyState title="No workspaces yet" hint="Create a workspace to register sources and run governed queries."/>:
    <div className="table-card"><table><thead><tr><th>Name</th><th>Description</th><th>Actions</th></tr></thead><tbody>
      {data.map((w:Obj)=><tr key={w.workspace_id}>
        <td><Link className="table-link" to={scope(w.workspace_id)+'/sources'}>{w.name}</Link></td>
        <td className="muted">{w.description||'-'}</td>
        <td className="button-row">
          <button className="btn btn-secondary" onClick={()=>change(w)}>Rename</button>
          <button className="btn btn-danger" onClick={()=>change(w,true)}>Archive</button>
        </td>
      </tr>)}
    </tbody></table></div>}
  </Shell>;
}

function NewWorkspace(){
  const[name,setName]=useState(''),[description,setDescription]=useState(''),[error,setError]=useState('');
  const nav=useNavigate();
  async function submit(e:FormEvent){
    e.preventDefault();
    try{
      const w=await request('/workspaces','POST',{name,description});
      nav(scope(w.workspace_id)+'/sources');
    }catch(e:any){setError(e.message)}
  }
  return <Shell title="Create workspace">
    <div className="form-card"><form onSubmit={submit}>
      <div className="field"><label className="field-label">Workspace Name</label><input required value={name} onChange={e=>setName(e.target.value)}/></div>
      <div className="field"><label className="field-label">Description</label><textarea value={description} onChange={e=>setDescription(e.target.value)}/></div>
      <ErrorBox message={error}/>
      <div className="form-actions"><button className="btn btn-primary">Create workspace</button></div>
    </form></div>
  </Shell>;
}

function statusBadge(status:string){
  const cls=status==='RUNNING'?'badge-info':status==='SUCCESS'||status==='ACTIVE'?'badge-success':status==='FAILED'||status==='PARTIAL'?'badge-danger':'badge-neutral';
  return <span className={'badge '+cls}>{status}</span>;
}

function Sources(){
  const{workspaceId=''}=useParams();
  const{data,error,reload}=useLoad(scope(workspaceId)+'/sources');
  const[issue,setIssue]=useState('');
  const[runs,setRuns]=useState<Record<string,Obj>>({});
  async function operate(source:Obj,op:string){
    try{
      if(op==='archive'){
        if(!confirm('Archive this source and retain its history?'))return;
        await request(scope(workspaceId)+'/sources/'+source.source_id,'DELETE');
      }else{
        const result=await request(scope(workspaceId)+'/sources/'+source.source_id+'/'+op,'POST');
        if(result.ingestion_run_id)setRuns(r=>({...r,[source.source_id]:result}));
        else alert('Connection successful');
      }
      reload();
    }catch(e:any){setIssue(e.message)}
  }
  useEffect(()=>{
    if(!Object.keys(runs).length)return;
    const timer=setInterval(()=>{
      Object.entries(runs).forEach(([sid,r])=>{
        if(r.status==='RUNNING')request(scope(workspaceId)+'/ingestion-runs/'+r.ingestion_run_id).then(next=>{
          setRuns(old=>({...old,[sid]:{...next,ingestion_run_id:r.ingestion_run_id}}));
          reload();
        }).catch(e=>setIssue(e.message));
      });
    },2500);
    return()=>clearInterval(timer);
  },[runs,workspaceId]);
  return <Shell title="Sources" actions={<Link className="btn btn-primary" to={scope(workspaceId)+'/sources/new'}>Register source</Link>}>
    <ErrorBox message={error||issue}/>
    {!data?<Loader/>:!data.length?<EmptyState title="No sources registered" hint="Register a source to begin ingestion."/>:
    <div className="table-card"><table><thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Latest ingestion</th><th>Actions</th></tr></thead><tbody>
      {data.map((s:Obj)=>{
        const status=runs[s.source_id]?.status||s.latest_ingestion?.status;
        const running=status==='RUNNING';
        return <tr key={s.source_id}>
          <td><Link className="table-link" to={scope(workspaceId)+'/sources/'+s.source_id}>{s.name}</Link></td>
          <td>{s.source_type.replaceAll('_',' ')}</td>
          <td>{s.enabled?<span className="badge badge-success">ACTIVE</span>:<span className="badge badge-neutral">DISABLED</span>}</td>
          <td>{status?statusBadge(status):<span className="muted">Never ingested</span>} {s.latest_ingestion?.started_at&&<span className="muted">{new Date(s.latest_ingestion.started_at).toLocaleString()}</span>}</td>
          <td className="button-row">
            <button className="btn btn-secondary" onClick={()=>operate(s,'test')}>Test</button>
            <button className="btn btn-secondary" disabled={!s.enabled||running} onClick={()=>operate(s,'ingest')}>Ingest</button>
            <button className="btn btn-danger" onClick={()=>operate(s,'archive')}>Archive</button>
          </td>
        </tr>;
      })}
    </tbody></table></div>}
  </Shell>;
}

function resolve(schema:Obj,root:Obj):Obj {
  if(schema.$ref)return root.$defs[schema.$ref.split('/').pop()];
  if(schema.anyOf)return resolve(schema.anyOf.find((x:Obj)=>x.type!=='null')||{},root);
  return schema;
}

function defaults(def:Obj){
  return Object.fromEntries(Object.entries(def.config_schema.properties).filter(([,v]:any)=>v.default!==undefined&&v.default!==null).map(([k,v]:any)=>[k,v.default]));
}

function SourceForm(){
  const{workspaceId='',sourceUuid}=useParams();
  const nav=useNavigate();
  const{data:catalog,error:catalogError}=useLoad('/source-types');
  const[name,setName]=useState(''),[type,setType]=useState(''),[credential,setCredential]=useState(''),[config,setConfig]=useState<Obj>({}),
    [schemas,setSchemas]=useState<string[]>([]),[search,setSearch]=useState(''),[all,setAll]=useState(true),[selected,setSelected]=useState<string[]>([]),
    [tested,setTested]=useState(false),[enabled,setEnabled]=useState(true),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const def=catalog?.find((x:Obj)=>x.source_type===type);
  useEffect(()=>{
    if(sourceUuid)request(scope(workspaceId)+'/sources/'+sourceUuid).then(s=>{
      setName(s.name);setType(s.source_type);setCredential(s.credential_ref);setConfig(s.config);setEnabled(s.enabled);
      setAll(s.config.schema_selection?.mode!=='selected');setSelected(s.config.schema_selection?.schemas||[]);
    }).catch(e=>setError(e.message));
  },[workspaceId,sourceUuid]);
  function field(k:string,value:any){setConfig(c=>({...c,[k]:value}));setTested(false)}
  async function discover(){
    setBusy(true);setError('');
    try{
      const clean={...config};delete clean.schema_selection;
      const r=await request(scope(workspaceId)+'/sources/discover','POST',{source_type:type,credential_ref:credential,config:clean});
      setSchemas(r.schemas);setTested(true);
    }catch(e:any){setError(e.message)}finally{setBusy(false)}
  }
  async function submit(e:FormEvent){
    e.preventDefault();setBusy(true);
    try{
      const final={...config};
      if(def.schema_capable)final.schema_selection={mode:all?'all':'selected',schemas:all?[]:selected};
      const payload={name,credential_ref:credential,config:final,...(sourceUuid?{enabled}:{source_type:type})};
      await request(scope(workspaceId)+'/sources'+(sourceUuid?'/'+sourceUuid:''),sourceUuid?'PATCH':'POST',payload);
      nav(scope(workspaceId)+'/sources');
    }catch(e:any){setError(e.message)}finally{setBusy(false)}
  }
  return <Shell title={sourceUuid?'Edit source':'Register source'}>
    <div className="form-card"><form onSubmit={submit}>
      <div className="field"><label className="field-label">Source Name</label><input required value={name} onChange={e=>setName(e.target.value)}/></div>
      <div className="field"><label className="field-label">Source Type</label>
        <select required disabled={!!sourceUuid} value={type} onChange={e=>{setType(e.target.value);setConfig(defaults(catalog.find((d:Obj)=>d.source_type===e.target.value)));setTested(false)}}>
          <option value="">Select a source type</option>
          {catalog?.map((d:Obj)=><option key={d.source_type} value={d.source_type}>{d.label}</option>)}
        </select>
      </div>
      <div className="field"><label className="field-label">Credential Reference</label><input required value={credential} onChange={e=>{setCredential(e.target.value);setTested(false)}}/></div>
      {def&&Object.entries(def.config_schema.properties).map(([k,raw]:any)=>{
        if(k==='schema_selection')return null;
        if(['account_url','tenant_id','client_id'].includes(k)&&type==='azure_blob'&&config.authentication!=='service_principal')return null;
        if(k==='folder_id'&&config.scope!=='folder'||k==='shared_drive_id'&&config.scope!=='shared_drive')return null;
        const s=resolve(raw,def.config_schema),required=def.config_schema.required?.includes(k);
        return <div className="field" key={k}>
          <label className="field-label">{s.title||k.replaceAll('_',' ')}</label>
          {s.enum?(k==='authentication'||k==='scope'?
            <div className="button-row">{s.enum.map((v:string)=><label key={v} style={{display:'flex',alignItems:'center',gap:6,fontWeight:500}}>
              <input type="radio" name={k} required={required} checked={config[k]===v} onChange={()=>{setConfig(c=>{
                const next:Obj={...c,[k]:v};
                if(k==='scope'){delete next.folder_id;delete next.shared_drive_id}
                if(k==='authentication'){delete next.account_url;delete next.tenant_id;delete next.client_id}
                return next;
              });setTested(false)}}/>{v.replaceAll('_',' ')}
            </label>)}</div>:
            <select value={config[k]??''} required={required} onChange={e=>field(k,e.target.value)}>
              <option value="">Select</option>{s.enum.map((v:string)=><option key={v}>{v}</option>)}
            </select>
          ):s.type==='boolean'?
            <label style={{display:'flex',alignItems:'center',gap:8}}><input type="checkbox" style={{width:'auto'}} checked={config[k]??false} onChange={e=>field(k,e.target.checked)}/>Enabled</label>:
            <input type={s.type==='integer'?'number':'text'} required={required} min={s.minimum} max={s.maximum} value={config[k]??''} onChange={e=>field(k,s.type==='integer'?Number(e.target.value):e.target.value)}/>
          }
        </div>;
      })}
      <div className="button-row" style={{marginBottom:19}}>
        <button type="button" className="btn btn-secondary" disabled={busy||!type||!credential} onClick={discover}>Test Connection / Discover</button>
        {tested&&<span className="badge badge-success">Connection successful</span>}
      </div>
      {def?.schema_capable&&<fieldset className="field" style={{border:'1px solid var(--line)',borderRadius:7,padding:14}}>
        <legend className="field-label" style={{padding:'0 6px'}}>Schemas</legend>
        <label style={{display:'flex',alignItems:'center',gap:8,marginBottom:10}}><input type="checkbox" style={{width:'auto'}} checked={all} onChange={e=>setAll(e.target.checked)}/>All schemas</label>
        {!all&&<><input aria-label="Search schemas" placeholder="Search schemas" value={search} onChange={e=>setSearch(e.target.value)}/>
          <div style={{display:'flex',flexDirection:'column',gap:6,marginTop:10}}>
            {schemas.filter(s=>s.toLowerCase().includes(search.toLowerCase())).map(s=><label key={s} style={{display:'flex',alignItems:'center',gap:8}}>
              <input type="checkbox" style={{width:'auto'}} checked={selected.includes(s)} onChange={e=>setSelected(old=>e.target.checked?[...old,s]:old.filter(x=>x!==s))}/>{s}
            </label>)}
          </div>
        </>}
      </fieldset>}
      {sourceUuid&&<label style={{display:'flex',alignItems:'center',gap:8,marginBottom:19}}><input type="checkbox" style={{width:'auto'}} checked={enabled} onChange={e=>setEnabled(e.target.checked)}/>Enabled</label>}
      <ErrorBox message={error||catalogError}/>
      <div className="form-actions"><button className="btn btn-primary" disabled={busy||!def||(!sourceUuid&&!tested)||!!def?.schema_capable&&!all&&!selected.length}>{sourceUuid?'Save changes':'Register source'}</button></div>
    </form></div>
  </Shell>;
}

function Proposals(){
  const{workspaceId=''}=useParams();
  const{data,error}=useLoad(scope(workspaceId)+'/proposals');
  return <Shell title="Proposals">
    <ErrorBox message={error}/>
    {!data?<Loader/>:!data.length?<EmptyState title="No proposals" hint="Proposals appear here after a successful ingestion run."/>:
    <div className="table-card"><table><thead><tr><th>Asset</th><th>Status</th></tr></thead><tbody>
      {data.map((p:Obj)=><tr key={p.proposal_id}>
        <td><Link className="table-link" to={scope(workspaceId)+'/proposals/'+p.proposal_id}>{p.machine_payload.asset_type} - {p.machine_payload.canonical_key}</Link></td>
        <td>{statusBadge(p.status)}</td>
      </tr>)}
    </tbody></table></div>}
  </Shell>;
}

function Readable({payload}:{payload:Obj}){
  return <dl>{Object.entries(payload).filter(([k,v])=>!k.endsWith('_id')&&!k.endsWith('_uuid')&&k!=='metadata'&&typeof v!=='object').map(([k,v])=>
    <div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{String(v)}</dd></div>
  )}</dl>;
}

function Proposal(){
  const{workspaceId='',proposalUuid=''}=useParams();
  const path=scope(workspaceId)+'/proposals/'+proposalUuid;
  const{data,error,reload}=useLoad(path);
  const[edits,setEdits]=useState<Obj>({}),[issue,setIssue]=useState('');
  async function act(action:string){
    try{
      await request(path+(action==='edit'?'':'/'+action),action==='edit'?'PATCH':'POST',action==='edit'?{payload:{...data.reviewed_payload,...edits}}:{});
      reload();
    }catch(e:any){setIssue(e.message)}
  }
  return <Shell title="Proposal review">
    <ErrorBox message={error||issue}/>
    {!data?<Loader/>:<div className="detail-card">
      <div className="status-line"><h2 style={{margin:0}}>{data.machine_payload.asset_type} - {data.machine_payload.canonical_key}</h2>{statusBadge(data.status)}</div>
      <Readable payload={data.reviewed_payload}/>
      {data.status==='PROPOSED'&&<>
        {Object.entries(data.reviewed_payload).filter(([k,v])=>typeof v==='string'&&!k.endsWith('_id')&&!['canonical_key','asset_type'].includes(k)).map(([k,v])=>
          <div className="field" key={k}><label className="field-label">{k}</label><textarea value={edits[k]??v} onChange={e=>setEdits({...edits,[k]:e.target.value})}/></div>
        )}
        <div className="form-actions">
          <button className="btn btn-secondary" onClick={()=>act('edit')}>Save review edits</button>
          <button className="btn btn-danger" onClick={()=>act('reject')}>Reject</button>
          <button className="btn btn-primary" onClick={()=>act('approve')}>Approve</button>
        </div>
      </>}
    </div>}
  </Shell>;
}

function Package(){
  const{workspaceId=''}=useParams();
  const path=scope(workspaceId)+'/package';
  const{data:info,error,reload}=useLoad(path);
  const{data:versions}=useLoad(path+'/versions');
  const[version,setVersion]=useState(''),[snapshot,setSnapshot]=useState<Obj|null>(null),[issue,setIssue]=useState('');
  useEffect(()=>{if(versions?.length&&!version)setVersion(String(versions[0].version))},[versions]);
  useEffect(()=>{if(version)request(path+'/versions/'+version).then(setSnapshot).catch(e=>setIssue(e.message))},[version,path]);
  async function rename(){
    const name=prompt('Package name',info.name);
    if(name)try{await request(path,'PATCH',{name});reload()}catch(e:any){setIssue(e.message)}
  }
  return <Shell title={info?.name||'Context package'} actions={<button className="btn btn-secondary" onClick={rename}>Rename package</button>}>
    <ErrorBox message={error||issue}/>
    <div className="field" style={{maxWidth:280}}>
      <label className="field-label">Version</label>
      <select value={version} onChange={e=>setVersion(e.target.value)}>
        <option value="">No approved version</option>
        {versions?.map((v:Obj)=><option key={v.version} value={v.version}>v{v.version}{v.status==='ACTIVE'?' - Active':''}</option>)}
      </select>
    </div>
    {!snapshot?<EmptyState title="No package version selected"/>:!snapshot.assets.length?<EmptyState title="This version has no assets"/>:
    <div className="asset-grid">{snapshot.assets.map((a:Obj)=><div className="asset-card" key={a.asset_revision_id}>
      <div className="asset-top"><span className="asset-type">{a.payload.asset_type}</span><span>{a.payload.canonical_key}</span></div>
      <Readable payload={a.payload}/>
      <p className="muted">Human approved</p>
      <div className="evidence-list">{a.evidence.map((e:Obj,i:number)=><div className="evidence-item" key={i}><span>{e.metadata?.original_filename||e.source_uri}</span></div>)}</div>
    </div>)}</div>}
  </Shell>;
}

function Citations({items}:{items:Obj[]}){
  if(!items?.length)return null;
  return <div className="evidence-list">{items.map((c,i)=><div className="evidence-item" key={i}>{c.label||'Source evidence'}</div>)}</div>;
}

function Query(){
  const{workspaceId=''}=useParams();
  const{data:workspace}=useLoad(scope(workspaceId));
  const[question,setQuestion]=useState(''),[result,setResult]=useState<Obj|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),
    [dialog,setDialog]=useState(false),[comment,setComment]=useState(''),[feedback,setFeedback]=useState('');
  async function run(e:FormEvent){
    e.preventDefault();setBusy(true);setError('');setResult(null);
    try{setResult(await request(scope(workspaceId)+'/query','POST',{question}));setFeedback('')}
    catch(e:any){setError(e.message)}finally{setBusy(false)}
  }
  async function vote(rating:string){
    try{
      await request(scope(workspaceId)+'/feedback','POST',{trace_id:result?.trace_id,rating,comment:rating==='BAD'?comment:''});
      setFeedback('Feedback saved');setDialog(false);
    }catch(e:any){setError(e.message)}
  }
  return <Shell title="Query" actions={<span className="muted">{workspace?.name||'Loading workspace...'}</span>}>
    <div className="form-card"><form onSubmit={run}>
      <div className="field"><label className="field-label">Question</label><textarea required value={question} onChange={e=>setQuestion(e.target.value)}/></div>
      <div className="form-actions"><button className="btn btn-primary" disabled={busy}>{busy?'Answering...':'Run Query'}</button></div>
    </form></div>
    <ErrorBox message={error}/>
    {result&&<section className="query-results">
      <div className="proof-banner">
        <div><span>Governed answer</span></div>
        <p style={{whiteSpace:'pre-wrap',color:'var(--ink)',fontSize:15}}>{result.answer}</p>
      </div>
      <div className="runtime-meta">
        <div><span>Package</span><strong style={{fontSize:15}}>{result.package.name} - v{result.package.version}</strong></div>
        <div><span>Status</span>{statusBadge(result.status)}</div>
        <div className="button-row" style={{alignItems:'center'}}>
          <button className="btn btn-ghost" aria-label="Thumbs up" onClick={()=>vote('GOOD')}>👍</button>
          <button className="btn btn-ghost" aria-label="Thumbs down" onClick={()=>setDialog(true)}>👎</button>
        </div>
      </div>
      <Citations items={result.citations}/>
      <SuccessBox message={feedback}/>
      <div className="response-details">{result.atomic_results.map((r:Obj,i:number)=><details key={i}>
        <summary>{r.question}</summary>
        <div className="branch-grid" style={{padding:'0 14px 14px'}}>{['context_on','context_off'].map(branch=><div className="branch-card" key={branch}>
          <div className="branch-head"><h3 className={branch==='context_off'?'context-off-title':''}>{branch==='context_on'?'Context ON':'Context OFF'}</h3>{statusBadge(r[branch].status)}</div>
          <p>{r[branch].answer||r[branch].message}</p>
          {r[branch].sql&&<pre className="sql-view">{r[branch].sql}</pre>}
          <Citations items={r[branch].citations}/>
          {r[branch].warnings.map((w:string)=><div className="warning-box" key={w}>{w}</div>)}
        </div>)}</div>
        <p className="muted" style={{padding:'0 14px 14px'}}>{r.proof.explanation}</p>
      </details>)}</div>
    </section>}
    {dialog&&<div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Negative feedback">
      <div className="modal">
        <div className="modal-head"><h3>What could be improved?</h3></div>
        <div className="modal-body"><textarea placeholder="Optional comment" value={comment} onChange={e=>setComment(e.target.value)}/></div>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={()=>setDialog(false)}>Cancel</button>
          <button className="btn btn-primary" onClick={()=>vote('BAD')}>Submit feedback</button>
        </div>
      </div>
    </div>}
  </Shell>;
}

export function AppRoutes(){
  return <Routes>
    <Route path="/" element={<Landing/>}/>
    <Route path="/workspaces" element={<Workspaces/>}/>
    <Route path="/workspaces/new" element={<NewWorkspace/>}/>
    <Route path="/workspaces/:workspaceId/sources" element={<Sources/>}/>
    <Route path="/workspaces/:workspaceId/sources/new" element={<SourceForm/>}/>
    <Route path="/workspaces/:workspaceId/sources/:sourceUuid" element={<SourceForm/>}/>
    <Route path="/workspaces/:workspaceId/proposals" element={<Proposals/>}/>
    <Route path="/workspaces/:workspaceId/proposals/:proposalUuid" element={<Proposal/>}/>
    <Route path="/workspaces/:workspaceId/package" element={<Package/>}/>
    <Route path="/workspaces/:workspaceId/query" element={<Query/>}/>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Routes>;
}
