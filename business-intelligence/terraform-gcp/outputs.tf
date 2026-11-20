output "service_account_email" {
  value       = google_service_account.bi_sync.email
  description = "Configure ADC for the backend with this service account using a secret-mounted credential or workload identity federation."
}

output "project_id" {
  value = var.project_id
}
