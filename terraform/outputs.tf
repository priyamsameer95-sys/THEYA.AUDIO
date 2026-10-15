output "service_url" {
  description = "The public HTTPS endpoint URL of the deployed theya.voice service."
  value       = google_cloud_run_v2_service.theya_voice.uri
}

output "data_bucket_name" {
  description = "The Cloud Storage bucket name for persistent database snapshots."
  value       = google_storage_bucket.theya_storage.name
}
