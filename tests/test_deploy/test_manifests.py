"""
Tests for the deployment manifests under ``deploy/`` (ROADMAP 6.2, Slice 3).

These are structural/lint tests: every Kubernetes manifest, the Prometheus
scrape config, the Grafana provisioning files, and the bundled dashboard JSON
must parse and carry the keys an operator relies on. The Helm chart is rendered
with ``helm template`` when the binary is available (skipped otherwise, so CI
without Helm stays green).

The manifests are shipped in the runtime image (Dockerfile ``COPY deploy/``), so
these tests run both locally and inside the container test suite.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy"
K8S = DEPLOY / "k8s"
HELM_CHART = DEPLOY / "helm" / "polaris-re"


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Kubernetes manifests
# ---------------------------------------------------------------------------


def test_deploy_directory_exists() -> None:
    assert DEPLOY.is_dir()
    assert K8S.is_dir()
    assert HELM_CHART.is_dir()


@pytest.mark.parametrize(
    ("filename", "kind"),
    [
        ("deployment.yaml", "Deployment"),
        ("service.yaml", "Service"),
        ("configmap.yaml", "ConfigMap"),
        ("ingress.yaml", "Ingress"),
    ],
)
def test_k8s_manifest_parses_with_expected_kind(filename: str, kind: str) -> None:
    doc = _load_yaml(K8S / filename)
    assert doc["kind"] == kind
    assert doc["apiVersion"]
    assert doc["metadata"]["name"]


def test_deployment_probes_and_metrics_annotations() -> None:
    doc = _load_yaml(K8S / "deployment.yaml")
    spec = doc["spec"]["template"]["spec"]
    container = spec["containers"][0]
    # Container listens on 8000 and both probes hit /health.
    assert container["ports"][0]["containerPort"] == 8000
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    # Prometheus scrape annotations point at the /metrics endpoint.
    annotations = doc["spec"]["template"]["metadata"]["annotations"]
    assert annotations["prometheus.io/scrape"] == "true"
    assert annotations["prometheus.io/path"] == "/metrics"
    assert annotations["prometheus.io/port"] == "8000"


def test_service_targets_container_http_port() -> None:
    doc = _load_yaml(K8S / "service.yaml")
    port = doc["spec"]["ports"][0]
    assert port["targetPort"] == "http"


def test_configmap_carries_default_off_security_knobs() -> None:
    data = _load_yaml(K8S / "configmap.yaml")["data"]
    # Present but blank → default-off (ADR-134/135); operator opts in.
    assert data["POLARIS_API_RATE_LIMIT"] == ""
    assert data["POLARIS_TRUSTED_PROXIES"] == ""


# ---------------------------------------------------------------------------
# Prometheus + Grafana
# ---------------------------------------------------------------------------


def test_prometheus_scrapes_api_metrics() -> None:
    cfg = _load_yaml(DEPLOY / "prometheus" / "prometheus.yml")
    jobs = cfg["scrape_configs"]
    job = next(j for j in jobs if j["job_name"] == "polaris-re-api")
    assert job["metrics_path"] == "/metrics"
    targets = job["static_configs"][0]["targets"]
    assert "api:8000" in targets


def test_grafana_datasource_points_at_prometheus() -> None:
    cfg = _load_yaml(DEPLOY / "grafana" / "provisioning" / "datasources" / "prometheus.yml")
    ds = cfg["datasources"][0]
    assert ds["type"] == "prometheus"
    assert ds["url"] == "http://prometheus:9090"


def test_grafana_dashboard_json_is_valid_and_queries_polaris_metrics() -> None:
    dash_path = DEPLOY / "grafana" / "dashboards" / "polaris-api.json"
    dashboard = json.loads(dash_path.read_text())
    assert dashboard["title"] == "Polaris RE API"
    exprs = " ".join(target["expr"] for panel in dashboard["panels"] for target in panel["targets"])
    assert "polaris_http_requests_total" in exprs
    assert "polaris_http_request_duration_seconds_bucket" in exprs


# ---------------------------------------------------------------------------
# Helm chart
# ---------------------------------------------------------------------------


def test_helm_chart_metadata_parses() -> None:
    chart = _load_yaml(HELM_CHART / "Chart.yaml")
    assert chart["name"] == "polaris-re"
    assert chart["version"]
    values = _load_yaml(HELM_CHART / "values.yaml")
    assert values["image"]["repository"] == "polaris-re"
    assert values["metrics"]["path"] == "/metrics"


def test_helm_template_renders_deployment_and_service() -> None:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm binary not available")
    result = subprocess.run(
        [helm, "template", "polaris-re", str(HELM_CHART)],
        capture_output=True,
        text=True,
        check=True,
    )
    kinds = {
        doc["kind"]
        for doc in yaml.safe_load_all(result.stdout)
        if isinstance(doc, dict) and "kind" in doc
    }
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "ConfigMap" in kinds
