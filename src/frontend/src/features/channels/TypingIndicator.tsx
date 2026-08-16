/**
 * "Ada is typing…".
 *
 * **Absent from the DOM when nobody is typing**, rather than rendered empty.
 * That is what lets a test wait for it to disappear rather than poll its text,
 * and it is also what stops an empty line reserving space under the composer.
 *
 * Names come from the workspace directory — the same hook every other name in
 * the UI goes through. The typing event carries only a user id, because
 * Messaging holds no names and two sources for one name is drift waiting to
 * happen.
 */

interface Props {
  names: string[]
}

function sentence(names: string[]): string {
  if (names.length === 1) return `${names[0]} is typing…`
  if (names.length === 2) return `${names[0]} and ${names[1]} are typing…`
  return 'Several people are typing…'
}

export function TypingIndicator({ names }: Props) {
  if (names.length === 0) return null

  return (
    <p
      data-testid="typing-indicator"
      aria-live="polite"
      className="px-4 pb-1 text-xs text-ink-muted italic"
    >
      {sentence(names)}
    </p>
  )
}
