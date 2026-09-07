export const DEFAULT_PRODUCT_PATH = '/workspace'
export const CHAT_PATH = '/chat'
export const YIELD_ESTIMATE_PATH = '/yield-estimate'

export function hasProductAccess(isAuthenticated: boolean, apiKey: string): boolean {
  return isAuthenticated || apiKey.trim().length > 0
}
