"""The images integration tests run are the images Compose runs.

`docker-compose.yml` is pinned from `docs/platform/versions.md`, and a test
container on a different tag would prove behaviour against a store nobody
deploys. Reads the file from disk — no network, no Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from testkit import dex, images

COMPOSE = Path(__file__).resolve().parents[5] / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose_images() -> dict[str, str]:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    return {name: service["image"] for name, service in services.items() if "image" in service}


@pytest.mark.parametrize(
    ("service", "pinned"),
    [
        ("postgres", "POSTGRES"),
        ("redis-cache", "REDIS"),
        ("redis-rt", "REDIS"),
        ("redis-streams", "REDIS"),
        ("elasticsearch", "ELASTICSEARCH"),
        ("dex", "DEX"),
    ],
)
def test_a_pinned_image_matches_compose(compose_images, service, pinned):
    assert getattr(images, pinned) == compose_images[service]


def test_dex_has_one_pin():
    assert dex.DEX_IMAGE == images.DEX
