"""`delivery` — the backends, for bash and for skills.

    delivery [--backend B] [--url U] check
    delivery [...] issue create --title T --body-file F [--label L ...]
    delivery [...] issue get KEY
    delivery [...] issue edit KEY --title T --body-file F
    delivery [...] issue verify KEY --title T --body-file F
    delivery [...] ensure-label NAME [--description D] [--color C]
    delivery [...] deliver KEY [--restart]
    delivery [...] prereqs
    delivery notify [--state STATE_JSON] [--broadcast] TEXT

`deliver` runs the delivery team on one issue — `scripts/deliver.sh` is its
wrapper, and `delivery.run`'s docstring is its reference. The backend is `--backend`/`--url`, else DELIVERY_BACKEND/DELIVERY_URL, else
local. Issues print as JSON. Exit 0 ok · 1 the backend failed, or verify found
differences · 2 bad configuration or usage. `deliver` adds 2 for a stop for a
human, and 3 for a stage with no agent yet.

`prereqs` checks what a delivery needs from this machine and, for GitHub, from the repo,
one line each, and exits 1 if anything required is missing — docs/delivery/prerequisites.md.

`notify` posts TEXT to Slack — SLACK_BOT_TOKEN and SLACK_CHANNEL — as a reply in the
delivery thread a run's `state.json` names, else to the channel; `preview.yml` posts its
preview's password through it. It always exits 0: Slack never fails what calls it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from delivery.errors import BackendError, ConfigError
from delivery.github import GitHubBackend, Runner
from delivery.local import LocalBackend
from delivery.model import Backend, Issue
from delivery.readback import differences
from delivery.resolve import GITHUB, BackendConfig, resolve

if TYPE_CHECKING:
    from delivery.run.notify import Transport

LABEL_DESCRIPTION = "Written for the delivery team (scripts/deliver.sh)"
LABEL_COLOR = "0e8a16"


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="delivery", description="Where delivery issues live.")
    cli.add_argument("--backend", help="local or github. Default: DELIVERY_BACKEND, else local")
    cli.add_argument("--url", help="the repo's web URL. Default: DELIVERY_URL")
    commands = cli.add_subparsers(dest="command", required=True)

    commands.add_parser("check", help="fail unless the backend can take a new issue")
    commands.add_parser("prereqs", help="check what a delivery needs, and say how to fix it")

    label = commands.add_parser("ensure-label", help="create a label, or update it")
    label.add_argument("name")
    label.add_argument("--description", default=LABEL_DESCRIPTION)
    label.add_argument("--color", default=LABEL_COLOR)

    notify = commands.add_parser("notify", help="post to the delivery's Slack thread")
    notify.add_argument("text")
    notify.add_argument("--state", type=Path, help="a run's state.json, for its thread")
    notify.add_argument("--broadcast", action="store_true", help="show the reply in the channel")

    run = commands.add_parser("deliver", help="run the delivery team on one issue, by its key")
    run.add_argument("key", help="issue-N for a local issue, gh-N for a GitHub one")
    run.add_argument("--restart", action="store_true", help="forget progress, start at plan-writer")

    issue = commands.add_parser("issue").add_subparsers(dest="action", required=True)
    create = issue.add_parser("create", help="create an issue; print it as the backend holds it")
    draft(create)
    create.add_argument("--label", action="append", default=[], dest="labels")
    issue.add_parser("get", help="print an issue").add_argument("key")
    for action, text in (
        ("edit", "replace an issue's title and body; print it"),
        ("verify", "exit 0 if the issue says what the draft says, else 1 and the differences"),
    ):
        command = issue.add_parser(action, help=text)
        command.add_argument("key")
        draft(command)
    return cli


def draft(command: argparse.ArgumentParser) -> None:
    command.add_argument("--title", required=True)
    command.add_argument("--body-file", required=True, type=Path)


def open_backend(config: BackendConfig, root: Path, run: Runner | None) -> Backend:
    if config.kind == GITHUB:
        assert config.url is not None  # noqa: S101 — resolve() refuses github without one.
        return GitHubBackend(config.url, run=run)
    return LocalBackend(root)


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    root: Path | None = None,
    run: Runner | None = None,
    slack_transport: Transport | None = None,
) -> int:
    args = parser().parse_args(argv)
    if args.command == "notify":
        return notify(args, os.environ if env is None else env, slack_transport)
    try:
        config = resolve(args.backend, args.url, os.environ if env is None else env)
        backend = open_backend(config, root or Path.cwd(), run)
        if args.command == "deliver":
            # Imported here: the runner is the CLI's largest command and the skill never needs it.
            from delivery.run import deliver

            return deliver(
                args.key,
                restart=args.restart,
                config=config,
                backend=backend,
                root=root or Path.cwd(),
                env=os.environ if env is None else env,
            )
        if args.command == "prereqs":
            return prereqs(config, backend, os.environ if env is None else env, root or Path.cwd())
        return dispatch(args, config, backend)
    except ConfigError as e:
        print(f"delivery: {e}", file=sys.stderr)  # noqa: T201
        return 2
    except BackendError as e:
        print(f"delivery: {e}", file=sys.stderr)  # noqa: T201
        return 1


def notify(args: argparse.Namespace, env: Mapping[str, str], transport: Transport | None) -> int:
    # Imported here, as `deliver` is: importing it loads the runner's package.
    from delivery.run.notify import notifier_from

    def say(message: str) -> None:
        print(f"delivery: {message}", file=sys.stderr)  # noqa: T201

    slack = notifier_from(env, transport=transport, log=say)
    if not slack.enabled:
        say("Slack isn't set up — SLACK_BOT_TOKEN and SLACK_CHANNEL — so nothing was posted")
        return 0
    thread = ""
    if args.state is not None:
        try:
            thread = str(json.loads(args.state.read_text()).get("slack_thread", ""))
        except (OSError, ValueError):
            thread = ""
    slack.post(args.text, thread=thread, broadcast=args.broadcast)
    return 0


def prereqs(config: BackendConfig, backend: Backend, env: Mapping[str, str], root: Path) -> int:
    from delivery import prereqs as check

    found = check.machine_checks(config.kind, env=env, root=root)
    if isinstance(backend, GitHubBackend):
        found += check.github_checks(backend)
    print(check.render(found))  # noqa: T201
    return 1 if any(c.state == check.MISSING for c in found) else 0


def dispatch(args: argparse.Namespace, config: BackendConfig, backend: Backend) -> int:
    if args.command == "check":
        backend.check()
        print(f"{config.kind}{f' {config.url}' if config.url else ''}: ok")  # noqa: T201
        return 0
    if args.command == "ensure-label":
        backend.ensure_label(args.name, args.description, args.color)
        return 0
    if args.action == "get":
        return show(backend.get(args.key))
    body = read_body(args.body_file)
    if args.action == "create":
        return show(backend.create(args.title, body, args.labels))
    if args.action == "edit":
        return show(backend.edit(args.key, args.title, body))
    found = differences(args.title, body, backend.get(args.key))
    print("\n".join(found) if found else "match")  # noqa: T201
    return 1 if found else 0


def read_body(path: Path) -> str:
    try:
        return path.read_text()
    except OSError as e:
        raise ConfigError(f"can't read the body file {path}: {e.strerror}") from e


def show(issue: Issue) -> int:
    print(json.dumps(issue.to_json(), indent=2, ensure_ascii=False))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
