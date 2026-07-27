# Worker gets job data from payloads and internal endpoints, never from service databases

- **Status:** Accepted
- **Date:** 2026-07-27

## Context

Two documents disagree about whether the Worker may read another service's
database. The platform conventions and the repository guidance are unambiguous
that every service owns its database and that cross-service reads go through the
owning service's API or through an event. The Worker design doc lists PostgreSQL
among its dependencies as "read-mostly", and describes the message indexing
handler as "read message (or accept payload)". Both cannot be true.

The contradiction stayed theoretical while nothing was built. Scaffolding forced
it: the Worker's settings object either has a `POSTGRES_DSN` or it does not, and
choosing meant choosing the architecture. The scaffold deliberately left it out
and deferred, which is what this record now settles.

It is worth being precise about what the Worker actually lacks, because "it needs
to read data" is true but too broad to design against. Of the seven job types,
three are already self-sufficient: thumbnail generation gets its `objectKey` in
the payload and reads bytes from object storage, which is shared infrastructure
the Worker is explicitly authorized to use; canvas document indexing receives a
text projection Canvas has already computed; retention sweeps carry only a scope.
The gaps are four. Message indexing receives `{messageId, op}` and needs the body,
channel, workspace and author to build an Elasticsearch document. Asset indexing
receives `{assetId}` and needs the file metadata. Notification dispatch needs
whatever address or preference the user has, which Auth owns. Canvas export needs
the full Yjs document state, which Canvas owns.

Retention is a fourth case that looks like the others and is not. Hard-deleting
soft-deleted rows past a policy is not a read at all — it is a write into tables
the Worker does not own, which no amount of read access would legitimise.

One relevant decision is already made. D14 settled that the Worker reports asset
variants back through `POST /api/v1/internal/assets/{id}/variants`, authenticated
with an Auth-issued service token. The machinery for a Worker to call an owning
service already exists and is already paid for.

## Decision

The Worker will hold no connection to any service's database. It gets what it
needs in one of two ways, chosen per job type.

**Where the producer already holds the data, it goes in the payload.** Messaging
has the message in hand at the moment it enqueues the index job; carrying the
whole indexable document costs one serialisation it was already doing. The same
applies to asset indexing. Index jobs therefore become self-describing: the
handler builds the Elasticsearch document from the envelope alone and reads
nothing back. This matters most precisely where it is applied, because message
indexing is the highest-volume job in the system.

**Where the data cannot travel in the payload, the Worker fetches it from the
owning service's internal endpoint**, using the service token mechanism from D14.
This covers notification dispatch, which needs user contact details Auth owns and
which the producer has no business copying into a job, and canvas export, which
needs document state far too large and too live to serialise into a stream entry.

**Retention inverts.** Rather than the Worker deleting rows, each service exposes
an internal sweep endpoint and executes its own deletions. The Worker's retention
handler triggers and reports; it does not know any service's schema. This keeps
the "a service owns its tables" rule intact for the one job type that would
otherwise break it outright.

Because index jobs now carry state rather than a pointer to it, they need an
ordering guard. Two rapid edits to the same message produce two jobs whose
payloads differ, and nothing about Redis Streams consumer groups guarantees the
second is processed after the first. Index jobs will therefore carry a
monotonically increasing version from the source row and use it as an
Elasticsearch external version, so a late-arriving older document is rejected
rather than applied. `messages` has no `version` column today, only `edited_at`;
adding one is part of implementing this.

## Consequences

The Worker becomes decoupled from four database schemas. This is the substantial
win and it compounds: any service can migrate its tables without a compatibility
check against the Worker, and the failure mode of a bad migration stays inside the
service that made it. A Worker that reads four schemas is a Worker that four teams
can break without knowing.

Jobs become self-describing, which pays off in operations rather than in
architecture. A dead-lettered entry can be understood, and often replayed, from
the stream alone, without reconstructing what the database looked like when it was
enqueued. Debugging asynchronous failures is meaningfully easier when the input is
in front of you.

Nothing new has to be built to make this work. Both halves — a job envelope and an
internal endpoint guarded by a service token — already exist as decided
mechanisms, so this is an application of D14 rather than a parallel path.

The costs are real and worth stating plainly.

Payloads grow. A message body may be 8000 characters, so index jobs go from tens
of bytes to roughly ten kilobytes, entirely in Redis memory on R3. At the message
volume this platform is designed for, stream trimming stops being a background
concern and becomes a capacity one — `MAXLEN` policies on `jobs:index` and its
dead-letter stream need setting deliberately rather than left to default.

User content now lives in Redis. Message bodies previously existed in Postgres and
Elasticsearch; they will now also sit in R3, in dead-letter streams, and in
whatever an engineer dumps while debugging a poison message. The conventions are
strict about PII in logs, and job payloads are adjacent enough to that boundary
that dead-letter retention and access need treating as handling user data, not as
operational exhaust.

Services acquire endpoints they would not otherwise have written: a retention
sweep on Messaging, Canvas and Asset, a document-state read on Canvas, and a user
lookup on Auth for notifications. That last one is the most likely to disappoint —
a notification fan-out becomes one call per recipient unless Auth offers a bulk
form, so it should be designed as a bulk endpoint from the start.

The coupling to Auth that D14 introduced now extends further. Notification and
export handlers join variant write-back in requiring a valid service token, so an
Auth outage delays more of the Worker's surface than before. The mitigation is
unchanged and still sound: unacknowledged jobs are reclaimed and retried, so the
failure mode is delay rather than loss.

Finally, this puts a standing obligation on producers. A handler that needs a new
field now requires a change in the producing service and a job envelope version
bump, not a wider `SELECT` in the Worker. That is more coordination per change,
and it is the price of the decoupling — the constraint is the point.

## Alternatives Considered

### Read-only access to service databases

What the Worker design doc implies, and the cheapest thing to write: give the
Worker a connection per database and let handlers query what they need.

Rejected because it contradicts the ownership rule the entire platform is built
on, and does so in the worst way — silently. A `SELECT` against another service's
table creates a dependency that appears in no interface, no contract and no test,
so the service that owns the table has no signal that anyone depends on its shape.
The Worker would end up coupled to four schemas at once, making it the single
component most likely to break during any team's migration. Taking this option
would mean amending the conventions deliberately rather than eroding them by
exception, and nothing about the Worker's needs justifies that.

### Internal endpoints for everything, with thin payloads

The most consistent option: keep job payloads as identifiers and have the Worker
read everything back through owning services' APIs, including messages.

Rejected on the hot path. Every message sent would generate an index job that
turns into an authenticated HTTP read back into Messaging, adding load to the
busiest service in the system in direct proportion to its busiest operation, to
retrieve a row the producer had in memory moments earlier. The consistency is
appealing and the cost lands exactly where the platform can least afford it. It
also re-reads state that may have changed since enqueue, which sounds like an
advantage until it means an edit and its index job disagree about ordering anyway.

### A read replica or shared read model

Give the Worker a read-only replica, or project service data into a read model it
owns.

Rejected on both counts. A replica is the same schema coupling with extra
infrastructure — the Worker still breaks when a table changes, it just breaks
against a copy. A properly owned read model is defensible architecture, but
building and maintaining projections for four services is far more work than the
four gaps here justify, and the fat-payload approach is the same idea at a
fraction of the cost.

### Domain events on a separate bus

Have services publish domain events that the Worker projects from, rather than
enqueueing jobs addressed to it.

Rejected as scope rather than as a bad idea. It is arguably where a larger system
lands, and fat payloads are a step in its direction — a job carrying full state is
an event in all but name. But it would mean a second transport alongside Redis
Streams, an event schema and its versioning, and a subscription model none of the
services currently need. Worth revisiting if the number of consumers of a given
state change ever exceeds one.
