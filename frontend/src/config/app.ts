export const appConfig = {
  apiBaseUrl: (
    import.meta.env.VITE_API_BASE_URL ||
    '/api'
  ).replace(/\/$/, ''),

  demoUsername:
    import.meta.env.VITE_DEMO_USERNAME ||
    'cce-admin',

  demoPassword:
    import.meta.env.VITE_DEMO_PASSWORD ||
    'cce-admin',

  actorId:
    import.meta.env.VITE_ACTOR_ID ||
    'cce-demo-user',

  actorRoles: (
    import.meta.env.VITE_ACTOR_ROLES ||
    'ADMIN,STEWARD'
  )
    .split(',')
    .map(
      (role: string) => role.trim(),
    )
    .filter(Boolean),
};