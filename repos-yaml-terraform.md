# Repositories, YAML, and Terraform — How They Work Together

## Overview

Think of it as three layers of a deployment system: the **repository** is the container, **Terraform** is the infrastructure brain, and **YAML** is the configuration and orchestration language.

---

## The Repository (the container)

A Git repo is the home for all your code and config files. It provides version control, collaboration, and the single source of truth for your entire stack.

A common structure looks like:

```
my-infra-repo/
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── .github/workflows/
│   └── deploy.yml        ← YAML (CI/CD pipeline)
├── kubernetes/
│   └── deployment.yaml   ← YAML (app config)
└── values.yaml           ← YAML (Helm chart values)
```

---

## Terraform Files — Provisioning Infrastructure

Terraform (`.tf` files) defines and provisions **cloud infrastructure** — servers, networks, databases, Kubernetes clusters, etc. It communicates directly with cloud provider APIs (AWS, GCP, Azure).

```hcl
# main.tf — provisions a Kubernetes cluster on GCP
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.region

  node_config {
    machine_type = "e2-medium"
  }
}
```

Terraform is **stateful** — it tracks what it has already created in a state file (`.tfstate`), so it knows what to add, change, or destroy on subsequent runs.

Key files:

| File | Purpose |
|---|---|
| `main.tf` | Core resource definitions |
| `variables.tf` | Input variable declarations |
| `outputs.tf` | Values exported after apply |
| `terraform.tfvars` | Variable values (often secret) |

---

## YAML Files — Two Distinct Roles

### 1. CI/CD Pipelines

YAML files define *when and how* Terraform (and other tooling) runs — triggered by git events like pushes or PR merges.

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Terraform Init
        run: terraform init
      - name: Terraform Apply
        run: terraform apply -auto-approve
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

### 2. App/Workload Configuration

Once Terraform has created the infrastructure (e.g., a Kubernetes cluster), YAML files configure what *runs on* that infrastructure.

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    spec:
      containers:
        - name: my-app
          image: my-app:latest
          ports:
            - containerPort: 8080
```

---

## How They Work Together — The Flow

```
Developer pushes code to repo
          ↓
CI/CD pipeline (YAML) triggers automatically
          ↓
Terraform runs → provisions infrastructure (cloud resources)
          ↓
Kubernetes/Helm YAML → deploys app onto that infrastructure
```

### Variable flow example

Terraform can output values (e.g., a cluster endpoint) that the pipeline captures and passes into Kubernetes YAML at deploy time:

```hcl
# outputs.tf
output "cluster_endpoint" {
  value = google_container_cluster.primary.endpoint
}
```

```yaml
# deploy.yml — capture Terraform output and use it
- name: Get cluster endpoint
  run: |
    ENDPOINT=$(terraform output -raw cluster_endpoint)
    kubectl config set-cluster my-cluster --server=https://$ENDPOINT
```

---

## Summary

| Layer | Tool | Role |
|---|---|---|
| Source of truth | Git Repository | Stores and versions everything |
| Infrastructure | Terraform (`.tf`) | Creates cloud resources |
| Orchestration | YAML (CI/CD) | Triggers and sequences automation |
| Configuration | YAML (K8s/Helm) | Defines what runs on infrastructure |

They are complementary, not competing: **Terraform handles "what exists," YAML handles "what runs and when."**
