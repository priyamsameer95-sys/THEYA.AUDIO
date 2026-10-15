terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Cloud Storage Bucket for Persistent DB Backups & Audio Asset Retention
resource "google_storage_bucket" "theya_storage" {
  name                     = "${var.project_id}-theya-data"
  location                 = var.region
  force_destroy            = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

# 2. Cloud Run Service (Production Single-Process Container)
resource "google_cloud_run_v2_service" "theya_voice" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = var.min_scale
      max_instance_count = var.max_scale
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
      }

      ports {
        container_port = 8000
      }

      env {
        name  = "PORT"
        value = "8000"
      }
      env {
        name  = "THEYA_SQLITE_PATH"
        value = "/data/theya.db"
      }

      startup_probe {
        http_get {
          path = "/api/voices"
          port = 8000
        }
        initial_delay_seconds = 2
        period_seconds        = 5
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/api/voices"
          port = 8000
        }
        period_seconds    = 15
        failure_threshold = 3
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    prevent_destroy = true
  }
}

# 3. Public Invocation Policy (Allows web client browser access)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  name     = google_cloud_run_v2_service.theya_voice.name
  location = google_cloud_run_v2_service.theya_voice.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
