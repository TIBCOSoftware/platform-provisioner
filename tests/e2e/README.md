# E2E Tests

End-to-end recipe tests that run inside the Docker runtime container.

## Scope

E2E tests exercise the full pipeline including Docker image, tool binaries, and real script execution. Each test is a recipe YAML file.

## Test Recipes

| Recipe | Requires | What it tests |
|--------|----------|---------------|
| `test-container-binaries.yaml` | Docker image | All tool versions (aws, az, helm, kubectl, etc.) |
| `test-container-binaries-on-prem.yaml` | Docker image | On-prem tool versions (no cloud CLIs) |
| `test-local.yaml` | Docker + k8s cluster | kubectl get nodes via on-prem kubeconfig |
| `test-retry.yaml` | Docker image | retryCount and retryDelay behavior |
| `test-aws.yaml` | Docker + AWS credentials | AWS STS assume role |
| `test-azure.yaml` | Docker + Azure credentials | Azure subscription access |
| `test-gcp.yaml` | Docker + GCP credentials | GCP project access |

## Running

```bash
# Default (test-container-binaries-on-prem)
make test-local

# Specific recipe
make test-local PIPELINE_INPUT_RECIPE=tests/e2e/test-retry.yaml
```

## Adding New E2E Tests

1. Create `test-<name>.yaml` as a recipe YAML in this directory
2. Set `apiVersion: v1` and `kind: generic-runner`
3. Run with `make test-local PIPELINE_INPUT_RECIPE=tests/e2e/test-<name>.yaml`
