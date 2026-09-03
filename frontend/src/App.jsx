import './styles.css'

const structure = [
  ['backend/app', 'CCE server / core implementation'],
  ['backend/app/api', 'REST API and routing'],
  ['backend/app/agents', 'Existing orchestration and ingestion agents'],
  ['backend/app/connectors', 'Enterprise source connectors'],
  ['backend/app/ingestion', 'Parsing and grounding pipeline'],
  ['backend/app/repository', 'Metadata persistence'],
  ['backend/app/integrations', 'AgenticPlane and external boundaries'],
  ['backend/app/mcp', 'MCP integration boundary'],
  ['backend/app/agent', 'AI-agent integration boundary'],
  ['backend/app/resources', 'MVP and architecture artifacts'],
  ['backend/app/tests', 'Existing CCE tests'],
  ['frontend', 'React UI — coming soon'],
]

export default function App() {
  return (
    <main className="shell">
      <section className="hero">
        <div className="eyebrow">COSTRATEGIX CONTEXT ENGINE</div>
        <h1>CCE Tool</h1>
        <p className="lead">Governed Context Server</p>
        <div className="badge">COMING SOON</div>
        <p className="copy">
          The CCE backend is being built as a plug-in server for applications,
          REST clients, MCP clients, and AI agents. The frontend will arrive
          after the core governed-context capabilities are complete.
        </p>
      </section>

      <section className="panel">
        <h2>Project structure</h2>
        <div className="tree">
          {structure.map(([path, description]) => (
            <div className="tree-row" key={path}>
              <code>{path}</code>
              <span>{description}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
