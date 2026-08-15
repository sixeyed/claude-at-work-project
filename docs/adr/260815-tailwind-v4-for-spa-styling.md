# Style the SPA with Tailwind CSS v4

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

Doc 06 §2 lists styling as "(team choice) Tailwind / CSS Modules" and the
register never picked it up, so this was an open question with no ID. It could
be left open while the SPA was a sign-in form — `src/index.css` was thirty lines
of scaffold that deliberately committed to nothing, and said so. Building the
chat shell forces the issue: a sidebar, a channel list with an active state, a
header, a form with inline validation errors, and a light/dark palette are not
things to style ad hoc and tidy up later.

The constraints are unremarkable and worth stating anyway. There is no
designer and no design system to implement, so whatever is chosen has to produce
a coherent result from developer judgement alone. The app is small now and will
grow through six more slices, so the styling approach has to survive components
being split and moved. And the SPA is built into a static bundle served by Nginx
(`docker/frontend/Dockerfile`), so anything requiring a runtime style server is
out.

## Decision

We will use **Tailwind CSS v4**, wired through `@tailwindcss/vite`.

v4 is a Vite plugin rather than a PostCSS pipeline, which is most of the reason
it wins over v3: there is no `tailwind.config.js` and no `postcss.config.js`, so
the whole setup is one line in `vite.config.ts` and an `@import "tailwindcss"`
at the top of `index.css`. The theme is defined in CSS with `@theme` rather than
in a JavaScript object, so the design tokens live next to the stylesheet that
uses them instead of in a config file at the project root.

The tokens are deliberately few — surface, border, ink, accent, danger. A
palette nobody references is a palette nobody maintains, so only the colours the
app actually uses are defined.

**The palette is light only.** An earlier draft carried a dark set under
`prefers-color-scheme`, and it was removed: following the OS setting is the easy
half of a theme feature, and the moment anyone wants to *override* it they need
somewhere to store the choice. There is no user-preferences feature anywhere in
the design — `users` carries a display name, an avatar reference and a status
(doc 01 §4), and `PATCH /users/me` updates the first two. Carrying a second
colour scheme means keeping it correct in every component built from here to the
end of the chat slices, in service of a setting no one can change. `body` sets
`color-scheme: light` so the browser's own widgets match rather than rendering
dark controls on a light page.

## Consequences

Styling is colocated with markup, which is the property that matters most as
components move between files: a component carries its appearance with it, and
there is no orphaned stylesheet left behind when one is deleted. There is no
naming problem to solve, which for a team without a design system removes a
steady source of bikeshedding.

The cost is markup that is noisier to read. A `className` with eight utilities
is harder to scan than a single semantic class name, and long lists of utilities
in JSX make diffs wider. Where the same combination repeats — and it does not
yet — the answer is a component, not an `@apply` rule; `@apply` recreates the
indirection Tailwind exists to remove.

Tailwind v4 requires a browser supporting `@property` and `color-mix()`, which
means recent Chrome, Safari and Firefox. That is fine for an app this team runs
locally and would need checking against a real browser support matrix before a
customer deployment.

The design-token layer is a commitment: components should use `text-ink-muted`
rather than a literal grey, or the theme stops meaning anything. This is the
same class of rule as the state boundary in the D24 record — easy to state, easy
to erode in review. It is also what keeps adding a dark palette later cheap: if
every component reads tokens, dark mode is one more `@theme` block, and if they
do not, it is a rewrite. That is the reason the rule matters even while there is
only one palette to be consistent with.

Users on a dark desktop get a light app with no way to change it. That is a real
cost, and the honest fix is a preferences feature rather than an OS-following
palette — which would leave the same users with no way to override the guess in
the other direction.

## Alternatives Considered

### CSS Modules

The other option doc 06 named, and a perfectly reasonable one: scoped class
names, ordinary CSS, no new vocabulary to learn, and no build plugin beyond what
Vite already does. It lost on the volume of small decisions it leaves open. Every
component needs class names invented and a file to put them in, and without a
design system to anchor them the result drifts — three slightly different greys
and two spacing scales, arrived at honestly. Tailwind's constraint is the point:
the scale is decided once.

### Plain CSS, extending the existing `index.css`

What the app does today. It works at thirty lines and does not work at three
hundred: no scoping means every rule is global, and a chat sidebar plus a
channel view plus a form is exactly where accidental cascade bugs start.

### A component library (MUI, Mantine, shadcn/ui)

Would supply finished components rather than just styling, which is genuinely
attractive for a dialog or a form. Rejected because the app needs very few
components so far, and adopting a library means adopting its theming system, its
opinions about composition, and a much larger dependency — for a sidebar, a list
and one form. Worth revisiting if a later slice needs real dialogs, menus and
overlays, where the accessibility work a library brings is not trivial to
reproduce.
