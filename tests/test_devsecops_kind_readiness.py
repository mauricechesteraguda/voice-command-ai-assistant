"""RED contracts for the focused local kind runtime readiness seams."""

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_tc_devops_0061_bootstraps_local_postgres_credentials_without_committed_values() -> None:
    manifest = (ROOT / "kind" / "local-services.yaml").read_text()
    bootstrap = (ROOT / "scripts" / "kind-up.sh").read_text()
    assert "secretRef" in manifest and "postgresql-credentials" in manifest
    assert "kubectl create secret generic postgresql-credentials" in bootstrap
    assert "--dry-run=client" in bootstrap
    assert "POSTGRES_PASSWORD=" not in manifest


def test_tc_devops_0062_provides_runnable_dex_config_issuer_clients_and_secret_mount() -> None:
    manifest = (ROOT / "kind" / "local-services.yaml").read_text()
    assert '"dex", "serve", "/etc/dex/config.yaml"' in manifest
    assert "configMap:" in manifest and "mountPath: /etc/dex" in manifest
    assert "issuer:" in manifest and "clientSecret:" not in manifest
    assert "secretRef:" in manifest
    assert "/healthz" in manifest


def test_tc_devops_0063_declares_control_plane_local_image_and_kind_load_contract() -> None:
    manifest = (ROOT / "kind" / "local-services.yaml").read_text()
    bootstrap = (ROOT / "scripts" / "kind-up.sh").read_text()
    assert "name: control-plane" in manifest
    assert "image: voice-command-ai-assistant:local" in manifest
    assert "imagePullPolicy: IfNotPresent" in manifest
    assert "kind load docker-image voice-command-ai-assistant:local" in bootstrap


def test_tc_devops_0064_runs_bounded_focused_kind_flow_in_static_dry_mode(tmp_path: Path) -> None:
    flow = ROOT / "scripts" / "kind-focused-flow.sh"
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    result = subprocess.run(
        [str(flow), "--dry-run", "--static"],
        cwd=ROOT,
        env={**os.environ, "RUNNER_TEMP": str(trace_dir)},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert all(
        marker in result.stdout
        for marker in ("api readiness", "enrollment", "signed config", "telemetry consent", "metrics")
    )
    assert not list(trace_dir.iterdir()), "external helper traces must be cleaned up"
