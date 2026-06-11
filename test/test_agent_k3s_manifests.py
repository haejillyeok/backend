from pathlib import Path

import yaml


def load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def test_agent_service_keeps_reverse_tunnel_node_port() -> None:
    service = load_yaml("deploy/k3s/agent-service.yaml")

    assert service["spec"]["type"] == "NodePort"
    assert service["spec"]["ports"][0]["nodePort"] == 31080


def test_agent_deployment_uses_monorepo_image_and_api_key_secret() -> None:
    deployment = load_yaml("deploy/k3s/agent-deployment.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    env_by_name = {item["name"]: item for item in container["env"]}

    assert pod_spec["nodeSelector"] == {"shiritori-role": "agent-storage"}
    assert container["image"] == "haejillyeok-backend:0.1.0"
    assert env_by_name["APP_MODULE"]["value"] == "agent"
    assert env_by_name["AGENT_API_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "agent-api-auth",
        "key": "api-key",
    }


def test_vllm_is_single_gpu_worker_replica_without_service_env_collision() -> None:
    deployment = load_yaml("deploy/k3s/vllm-deployment.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert deployment["spec"]["replicas"] == 1
    assert pod_spec["enableServiceLinks"] is False
    assert pod_spec["runtimeClassName"] == "nvidia"
    assert container["args"][0] == "/models/Qwen3.5-9B"
    assert container["args"].count("serve") == 0
    assert container["resources"]["limits"]["nvidia.com/gpu"] == "1"


def test_kustomization_does_not_publish_company_cluster_ingress() -> None:
    kustomization = load_yaml("deploy/k3s/kustomization.yaml")

    assert "agent-ingress.yaml" not in kustomization["resources"]
