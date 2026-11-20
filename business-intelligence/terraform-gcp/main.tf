resource "google_project_service" "bigquery" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "bi_sync" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "StreamShield tenant-isolated BigQuery analytics sync"
  description  = "Creates one BigQuery dataset per tenant and replaces its analytics tables."
}

resource "google_project_iam_member" "bi_sync_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.bi_sync.email}"
}
