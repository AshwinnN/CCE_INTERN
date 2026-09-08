export function Loader({ label='Loading…' }: { label?: string }) { return <div className="loader-wrap"><span className="spinner"/><span>{label}</span></div> }
