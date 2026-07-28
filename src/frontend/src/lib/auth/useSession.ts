/**
 * React's view of the session store.
 *
 * `useSyncExternalStore` rather than a context and `useState`: the store lives
 * outside React because a token renewal fires from a timer, not from a render.
 */

import { useSyncExternalStore } from 'react'

import { snapshot, subscribe, type State } from './session'

export function useSession(): State {
  return useSyncExternalStore(subscribe, snapshot)
}
