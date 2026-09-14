"""Bootstrap a fresh single-node Garage on the local k3d cluster.

Run by the post-install/post-upgrade Job in `templates/garage.yaml`. It does what
README.md lists as manual steps for Compose — assign a layout, create the bucket,
import the key, grant it — through Garage's admin API, because the Garage image
has no shell to run its own CLI from.

Every step checks before it acts, so it is safe on every upgrade. Standard
library only: the Job runs it in a stock Python image.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

ADMIN_URL = os.environ["GARAGE_ADMIN_URL"].rstrip("/")
ADMIN_TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
BUCKET = os.environ["GARAGE_BUCKET"]
ACCESS_KEY_ID = os.environ["GARAGE_ACCESS_KEY_ID"]
SECRET_ACCESS_KEY = os.environ["GARAGE_SECRET_ACCESS_KEY"]
CAPACITY_BYTES = int(os.environ["GARAGE_CAPACITY_BYTES"])
ZONE = "dc1"

log = logging.getLogger("garage-bootstrap")


class NotFoundError(Exception):
    """The admin API answered 404."""


class NotReadyError(Exception):
    """Garage is up but cannot serve this call yet — usually a layout still settling."""


def call(endpoint: str, body: dict[str, Any] | None = None, **query: str) -> Any:
    url = f"{ADMIN_URL}/v2/{endpoint}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(  # noqa: S310 — a fixed in-cluster http URL
        url,
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFoundError(endpoint) from None
        # Garage answers 500 "Layout not ready" for a few seconds after a layout
        # is applied, so anything but a 404 is worth another try.
        raise NotReadyError(f"{endpoint}: HTTP {exc.code}") from None
    return json.loads(payload) if payload else None


def retry[T](step: str, action: Callable[[], T], attempts: int = 60) -> T:
    """Retry while Garage starts, and while a newly applied layout settles."""
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except (NotReadyError, urllib.error.URLError) as exc:
            if attempt == attempts:
                raise SystemExit(
                    f"{step}: Garage still not ready after {attempts} attempts ({exc})"
                ) from None
            time.sleep(2)
    raise AssertionError("unreachable")


def ensure_layout(node_id: str) -> None:
    layout = call("GetClusterLayout")
    if any(role["id"] == node_id for role in layout["roles"]):
        log.info("layout: already assigned")
        return
    version = layout["version"] + 1
    role = {"id": node_id, "zone": ZONE, "capacity": CAPACITY_BYTES, "tags": []}
    call("UpdateClusterLayout", {"roles": [role]})
    call("ApplyClusterLayout", {"version": version})
    log.info("layout: assigned the node and applied version %d", version)


def ensure_bucket() -> str:
    try:
        bucket = call("GetBucketInfo", globalAlias=BUCKET)
        log.info("bucket: %s already exists", BUCKET)
    except NotFoundError:
        bucket = call("CreateBucket", {"globalAlias": BUCKET})
        log.info("bucket: created %s", BUCKET)
    return bucket["id"]


def ensure_key() -> None:
    try:
        call("GetKeyInfo", id=ACCESS_KEY_ID)
        log.info("key: already imported")
    except NotFoundError:
        call(
            "ImportKey",
            {
                "accessKeyId": ACCESS_KEY_ID,
                "secretAccessKey": SECRET_ACCESS_KEY,
                "name": "collabhub-local",
            },
        )
        log.info("key: imported")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    node_id = retry("status", lambda: call("GetClusterStatus")["nodes"][0]["id"])
    retry("layout", lambda: ensure_layout(node_id))
    bucket_id = retry("bucket", ensure_bucket)
    retry("key", ensure_key)
    # Granting is idempotent in Garage, so there is nothing to check first.
    permissions = {"read": True, "write": True, "owner": False}
    retry(
        "allow",
        lambda: call(
            "AllowBucketKey",
            {"bucketId": bucket_id, "accessKeyId": ACCESS_KEY_ID, "permissions": permissions},
        ),
    )
    log.info("allow: the key can read and write %s", BUCKET)


if __name__ == "__main__":
    main()
