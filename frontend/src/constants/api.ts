export const API = {
  V2: {
    TOOLS: '/v2/tools',
    AGENTS: '/v2/agents',
    PACKS: '/v2/domain-packs',
    SESSIONS: '/v2/sessions',
    UPLOAD: '/v2/upload',
    RUNS: '/v2/runs',
    ARTIFACTS: '/v2/artifacts',
    DATASETS: '/v2/datasets',
    SYSTEM: '/v2/system',
    AUTH: {
      LOGIN: '/v2/auth/login',
      REGISTER: '/v2/auth/register',
      ME: '/v2/auth/me',
    },
    PLUGINS: {
      TOOLS: '/v2/plugins/tools',
    },
  },
  HEALTH: '/health',
} as const

export type ApiPath = typeof API
