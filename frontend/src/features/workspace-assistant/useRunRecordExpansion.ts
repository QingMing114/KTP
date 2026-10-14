import { useState } from 'react'

/** A manual choice lasts for this chat turn; the next user turn resets it. */
export function useRunRecordExpansion(round: string, automatic: boolean) {
  const [choice, setChoice] = useState<{ round: string; expanded: boolean } | null>(null)
  const expanded = choice?.round === round ? choice.expanded : automatic
  return { expanded, toggle: () => setChoice({ round, expanded: !expanded }) }
}
