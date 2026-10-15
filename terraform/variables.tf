variable "project_id" {
  type        = string
  description = "The Google Cloud project ID where theya.voice is deployed."
  default     = "theya-voice-prod"
}

variable "region" {
  type        = string
  description = "The GCP region for the container service."
  default     = "us-central1"
}

variable "service_name" {
  type        = string
  description = "The Cloud Run service name."
  default     = "theya-voice"
}

variable "container_image" {
  type        = string
  description = "The container image URI for theya.voice."
  default     = "gcr.io/theya-voice-prod/theya-voice:v0.1.0"
}

variable "cpu_limit" {
  type        = string
  description = "CPU allocated per container instance."
  default     = "1000m"
}

variable "memory_limit" {
  type        = string
  description = "Memory allocated per container instance."
  default     = "1024Mi"
}

variable "min_scale" {
  type        = number
  description = "Minimum number of container instances kept warm."
  default     = 1
}

variable "max_scale" {
  type        = number
  description = "Maximum number of container instances during peak traffic."
  default     = 10
}
