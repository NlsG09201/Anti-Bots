variable "project_id" {
  description = "Existing Google Cloud project with billing enabled."
  type        = string
}

variable "region" {
  description = "Default Google Cloud region. BigQuery location is set separately in the application."
  type        = string
  default     = "us-central1"
}

variable "service_account_id" {
  type    = string
  default = "streamshield-bi-sync"
}
