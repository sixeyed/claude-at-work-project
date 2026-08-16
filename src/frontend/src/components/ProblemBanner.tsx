/**
 * One place that renders a failure to a user.
 *
 * Every non-2xx on this platform is an RFC 7807 Problem Details document
 * (Conventions §4.2), and `lib/api/client.ts` has already turned it into a
 * `ProblemError`. What is left is deciding what to show, and that decision
 * should not be made three times in three components: the `title` says what
 * class of thing went wrong, the `detail` says what actually happened, and
 * anything that is not a problem document at all still has to say something.
 *
 * Field-level messages are *not* rendered here. `errors.name` belongs against
 * the name input (doc 06 §7), so a form pulls it out with `fieldError` and this
 * banner carries what is left over — the 409s and the 403s with nowhere else to
 * go.
 */

import { describeError, ProblemError } from '../lib/api/client'

interface Props {
  error: unknown
}

export function ProblemBanner({ error }: Props) {
  if (!error) return null

  const problem = error instanceof ProblemError ? error : undefined

  return (
    <p
      data-testid="problem-banner"
      role="alert"
      className="rounded bg-danger-surface px-3 py-2 text-sm text-danger"
    >
      {problem ? problem.message : describeError(error)}
    </p>
  )
}
