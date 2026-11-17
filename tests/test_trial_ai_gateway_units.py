"""The trial AI gateways listen on loopback only (scripts/install_trial_ai_gateways.sh, RELEASE_0.11.05.md step 1).

Static checks of what the installer writes to the server: each systemd unit binds 127.0.0.1, none names an
all-interfaces address, and the one host forwarder (compose's ai-host-bridge) listens on the ai-host bridge's
gateway address, the same address the installer's check and firewall rule use.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_trial_ai_gateways.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.unit

ALL_INTERFACES = re.compile(r"0\.0\.0\.0|\[::\]|(?<![\w.])::(?![\w:])|\*:")


def _units() -> dict[str, str]:
    text = INSTALLER.read_text(encoding="utf-8")
    return dict(re.findall(r"write_unit (\S+\.service) <<'UNIT'.*?\n(.*?)\nUNIT\n", text, flags=re.S))


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))


def test_the_installer_writes_both_gateway_units():
    assert set(_units()) == {"mdarix-freellmapi.service", "mdarix-omniroute.service"}


@pytest.mark.parametrize(
    ("unit", "host_setting", "port"),
    [("mdarix-freellmapi.service", "HOST", "3011"), ("mdarix-omniroute.service", "OMNIROUTE_SERVER_HOST", "20128")],
)
def test_every_unit_binds_loopback_and_never_all_interfaces(unit, host_setting, port):
    text = _units()[unit]
    assert f"Environment={host_setting}=127.0.0.1" in text.splitlines()
    assert f"Environment=PORT={port}" in text.splitlines()
    assert not ALL_INTERFACES.search(text), text
    assert "User=mdarix-gw" in text and "User=root" not in text


def test_omniroute_requires_its_access_key_and_has_no_cloud_sync():
    lines = _units()["mdarix-omniroute.service"].splitlines()
    assert "Environment=REQUIRE_API_KEY=true" in lines
    assert "Environment=CLOUD_URL=" in lines


def test_the_host_forwarder_listens_on_the_ai_host_bridge_gateway_only():
    compose = _compose()
    gateway = compose["networks"]["ai-host"]["ipam"]["config"][0]["gateway"]
    command = compose["services"]["ai-host-bridge"]["command"]
    assert command[command.index("--listen") + 1] == gateway
    assert not ALL_INTERFACES.search(" ".join(command))
    installer = INSTALLER.read_text(encoding="utf-8")
    assert f"BRIDGE_ADDRESS={gateway}\n" in installer


@pytest.mark.skipif(BASH is None, reason="needs bash")
@pytest.mark.parametrize("script", ["install_trial_ai_gateways.sh", "enter_trial_ai_keys.sh"])
def test_the_server_scripts_parse(script):
    result = subprocess.run([BASH, "-n", (ROOT / "scripts" / script).as_posix()], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
