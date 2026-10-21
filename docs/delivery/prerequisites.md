# Delivery prerequisites

What `scripts/deliver.sh` and the GitHub Actions workflows need before a delivery can run,
for a person setting it up and for an agent checking it. One command checks all of it:

```bash
uv run delivery prereqs                                                    # the local backend
uv run delivery --backend github --url https://github.com/OWNER/REPO prereqs
```

It prints one line per prerequisite: ✔ in place, ✗ missing, with a link to the section
below that says how to fix it, and ○ for an optional one that isn't set up. It exits 1 if
anything required is missing, so a script or an agent can gate on it. It reads only names
and settings, never a secret's value.

The local backend (`issue-N`, `docs/issues/NNN.md`) needs only [the machine](#the-machine).
The GitHub backend (`gh-N`) needs everything below. A delivery on a hosted runner needs the
repo's side, and a delivery run from a laptop against GitHub needs both sides.

## The machine

Where `scripts/deliver.sh` runs. A laptop, or the hosted runner, which `deliver.yml` sets up
itself. The runner's pre-flight refuses to start without these, and lists them all at once:

- `claude`, `git`, `uv`, `node`, `npm`, `python3`: the workflow and what its stages run.
- `docker` with a reachable daemon and `docker compose` v2: the e2e layer's stack.
- `helm`, `k3d`, `kubectl`, `curl`, `cloudflared`: the acceptance-reviewer's preview.
- `htpasswd`, only when Slack is set up: a preview's own password is bcrypted with it. It
  ships with macOS, and on Debian or Ubuntu it is in `apache2-utils`.
- `.env.example` at the repo root.

## gh, signed in

The GitHub backend calls the `gh` CLI for everything: it fetches issues, and it opens,
updates and drafts PRs, comments on them, and dispatches `preview.yml`. Install it
(https://cli.github.com) and sign in:

```bash
gh auth login        # scopes: repo, workflow
gh auth status
```

On the hosted runner, `GH_TOKEN` is the job's own token, with the permissions the workflow
asks for. Nothing to set up.

## The repo

- **Issues are on**, and **you can write to the repo**: a delivery reads its issue, and the
  issue-writer skill creates issues and labels.
- **Actions are enabled.**

## Claude's secret

One of these repo secrets, for the agents on the hosted runner. Settings → Secrets and
variables → Actions, or:

```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN -R OWNER/REPO     # from `claude setup-token`
gh secret set ANTHROPIC_API_KEY -R OWNER/REPO           # or an API key
```

A stub run (`deliver.yml`'s `stub` input) runs no model and needs neither.

## Actions may open pull requests

An accepted delivery opens its PR with the job's own token. Settings → Actions → General →
*Workflow permissions* → **Allow GitHub Actions to create and approve pull requests**.

If the checkbox is greyed out, the organisation forbids it. An owner allows it first, at
`https://github.com/organizations/ORG/settings/actions`, and then it can be ticked on the repo.

## Squash merges only

A delivery's PR carries its screenshots in two commits of their own: one adds them, the next
removes them. Only a squash merge keeps those commits, and their images, out of `main`'s
history (ADR `261019-delivery-opens-its-pr`). Settings → General → *Pull Requests*: allow
**squash merging** only, and **automatically delete head branches**. Or:

```bash
gh api -X PATCH repos/OWNER/REPO -F allow_squash_merge=true -F allow_merge_commit=false \
    -F allow_rebase_merge=false -F delete_branch_on_merge=true
```

## The workflows, on the default branch

`.github/workflows/deliver.yml` runs a delivery, and `preview.yml` holds a PR's preview. GitHub
dispatches a workflow only from the default branch, so both have to be on `main`.

## Slack (optional)

With Slack set up, a delivery reports to one thread per delivery: each stage starting and
ending, stops, failures and the PR. Each preview also gets a random password, posted in that
thread and nowhere else. Without it, nothing is posted and every preview keeps the shared
password `collabhub`, which anyone who reads a public PR can use.

1. At https://api.slack.com/apps, **Create New App → From a manifest**, with:
   ```yaml
   display_information:
     name: CollabHub Delivery
     description: Posts delivery runs and preview passwords
   features:
     bot_user:
       display_name: delivery
       always_online: false
   oauth_config:
     scopes:
       bot:
         - chat:write
   settings:
     org_deploy_enabled: false
     socket_mode_enabled: false
     token_rotation_enabled: false
   ```
2. **Install to Workspace**. Then go to **OAuth & Permissions** and copy the **Bot User OAuth
   Token** (`xoxb-…`).
3. Make a **private** channel, say `#deliveries`. Its members are everyone who can sign in to
   a preview. Run `/invite @delivery` in it. Its ID (`C…`) is at the bottom of the channel's
   details.
4. Set both repo secrets. Both, or neither: one alone is a mistake the check reports.
   ```bash
   gh secret set SLACK_BOT_TOKEN -R OWNER/REPO
   gh secret set SLACK_CHANNEL -R OWNER/REPO
   ```

For a run on a laptop, export the same two variables. They stay with the runner: no agent is
given them.
