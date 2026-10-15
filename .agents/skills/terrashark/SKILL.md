---
name: terrashark
description: Diagnostic and best-practice engine for Terraform and Infrastructure-as-Code (IaC) grounded in HashiCorp official recommendations.
---

# TerraShark: Terraform & IaC Diagnostics

A diagnostic workflow designed to identify failure modes, enforce resource lifecycle controls, and ensure composable, drift-free Infrastructure-as-Code.

## The TerraShark Diagnostic Sequence

```
[1. Capture Context] ──► [2. Identify Failure Mode] ──► [3. Load HashiCorp Standard] ──► [4. Propose Fix with Risk Controls] ──► [5. Validate Plan]
```

### 1. Capture Context
- Identify current Terraform version, target cloud provider (AWS, Azure, GCP), and backend state configuration (S3, Terraform Cloud).

### 2. Failure Mode Identification
- Classify the issue:
  - State drift / resource recreation on unchanged configurations.
  - Cycle dependency in resource graph.
  - Missing lifecycle prevention (`prevent_destroy`, `ignore_changes`).
  - Hardcoded variables or unparameterized environment values.

### 3. HashiCorp Standard Alignment
- When conflicts arise between community hacks and HashiCorp official recommendations, **always side with HashiCorp**.
- Prefer native resource attributes over `local-exec` or provisioner scripts.

### 4. Explicit Risk Controls & Lifecycle Rules
- Always declare `lifecycle { prevent_destroy = true }` on stateful production data stores (RDS, DynamoDB, Cloud SQL, S3 buckets).
- Use `create_before_destroy = true` for zero-downtime updates on certificates, launch templates, and network bindings.

### 5. Plan Validation
- Run `terraform validate` and `terraform plan`.
- Audit plan output for unexpected resource destructions (`-`) before any `apply`.
