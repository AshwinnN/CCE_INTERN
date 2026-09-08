import type { ReactNode } from 'react'
export function Field({ label, required, error, children, hint }: { label:string; required?:boolean; error?:string; hint?:string; children:ReactNode }) { return <label className="field"><span className="field-label">{label}{required && <b> *</b>}</span>{children}{hint && <small>{hint}</small>}{error && <span className="field-error">{error}</span>}</label> }
