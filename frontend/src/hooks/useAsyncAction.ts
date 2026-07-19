import { useState, useCallback, useRef } from 'react'

/**
 * Generic async action hook — eliminates repetitive loading/error state management.
 *
 * Usage:
 *   const { execute, loading, error, data } = useAsyncAction(api.listKnowledgeDocuments)
 *   await execute()           // calls the function
 *   if (error) showToast(error)
 */
export function useAsyncAction<T, A extends unknown[] = []>(
  action: (...args: A) => Promise<T>,
) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<T | null>(null)
  const actionRef = useRef(action)
  actionRef.current = action

  const execute = useCallback(async (...args: A): Promise<T | null> => {
    setLoading(true)
    setError(null)
    try {
      const result = await actionRef.current(...args)
      setData(result)
      return result
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setLoading(false)
    setError(null)
    setData(null)
  }, [])

  return { execute, loading, error, data, reset }
}
