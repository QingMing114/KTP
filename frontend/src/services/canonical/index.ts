/** Canonical API client modules — /api/product/v1 protocol.
 *
 * These clients replace the legacy ``/v2/*`` calls in ``services/api.ts``.
 * Each module is self-contained, typed, and ready for incremental adoption.
 *
 * Usage:
 *   import { getConversation, createSubmission } from '../services/canonical'
 */

export * from './manifestClient'
export * from './conversationClient'
export * from './datasetClient'
export * from './submissionClient'
export * from './runClient'
export * from './artifactClient'
export * from './debugClient'
