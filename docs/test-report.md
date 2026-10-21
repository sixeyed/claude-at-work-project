# Test report

Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost. Revision `56fb009602cc-dirty`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ✅ passed | | | | `56fb009602cc-dirty` |
| Unit | ✅ passed | 1993 | 0 | 0 | `56fb009602cc-dirty` |
| Integration | ✅ passed | 627 | 0 | 0 | `56fb009602cc-dirty` |
| End-to-end | ✅ passed | 25 | 0 | 0 | `56fb009602cc-dirty` |

## Failures

None.

## Journeys

### Channels

4 of 4 passed.

| Scenario | Result |
|---|---|
| Ada signs in and sees her workspace | ✅ passed |
| Ada creates a public channel and lands in it | ✅ passed |
| A new public channel appears for another member | ✅ passed |
| Ada creates a private channel and only she can see it | ✅ passed |

### Direct messages

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees the direct message Ada starts, and replies | ✅ passed |

### Display names

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees the name Alan chose on his message | ✅ passed |

### File attachments

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees the image and the PDF Ada sends | ✅ passed |

### Messages

4 of 4 passed.

| Scenario | Result |
|---|---|
| Ada sends a message and sees it in the channel | ✅ passed |
| Grace sees Ada's message after reloading | ✅ passed |
| Ada edits her own message and it shows an edited marker | ✅ passed |
| Ada deletes her own message and a tombstone remains after reload | ✅ passed |

### Permissions

3 of 3 passed.

| Scenario | Result |
|---|---|
| An admin adds a member to a private channel and they can see it | ✅ passed |
| Removing a member revokes their view of the private channel | ✅ passed |
| A non-member cannot open a private channel by its URL | ✅ passed |

### Reactions

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees Ada's reaction without reloading | ✅ passed |

### Read state

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace's unread count clears once she has read the channel | ✅ passed |

### Real-time delivery

4 of 4 passed.

| Scenario | Result |
|---|---|
| Grace sees Ada's message without reloading | ✅ passed |
| Ada's edit propagates to Grace live | ✅ passed |
| Ada's delete propagates to Grace live | ✅ passed |
| The stream recovers after the connection drops | ✅ passed |

### Search

1 of 1 passed.

| Scenario | Result |
|---|---|
| Ada finds a message and opens it in its channel | ✅ passed |

### Sessions

3 of 3 passed.

| Scenario | Result |
|---|---|
| Ada signs out and stays signed out after reloading | ✅ passed |
| Following a channel link without signing in asks for sign-in | ✅ passed |
| Ada switches workspace and leaves the demo channels behind | ✅ passed |

### Threads

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees Ada's reply in a thread without reloading | ✅ passed |

## By service

| Service | Unit | Integration |
|---|---|---|
| asset | ✅ 39 passed | ✅ 34 passed |
| auth | ✅ 116 passed | ✅ 171 passed |
| canvas | ✅ 2 passed | — |
| messaging | ✅ 136 passed | ✅ 325 passed |
| other | ✅ 889 passed | ✅ 48 passed |
| shared | ✅ 94 passed | ✅ 26 passed |
| testkit | ✅ 130 passed | ✅ 6 passed |
| worker | ✅ 19 passed | ✅ 17 passed |
| frontend | ✅ 568 passed | — |

## Coverage

Unit tests only.

| Package | Lines | Branches |
|---|---|---|
| asset | `██████░░░░` 66% | `█████░░░░░` 54% |
| auth | `██████░░░░` 61% | `██░░░░░░░░` 23% |
| canvas | `█████████░` 96% | — |
| contracts | `██████████` 100% | — |
| messaging | `█████░░░░░` 56% | `███░░░░░░░` 31% |
| shared | `█████████░` 90% | `███████░░░` 75% |
| worker | `██████░░░░` 65% | `███░░░░░░░` 30% |
| frontend | `█████████░` 97% | `████████░░` 88% |
