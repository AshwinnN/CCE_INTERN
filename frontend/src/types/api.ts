export interface Workspace { workspace_id: string; name: string; description: string; status: 'ACTIVE' | 'ARCHIVED' }
export interface Citation { label: string; coordinates: Record<string, unknown> }
