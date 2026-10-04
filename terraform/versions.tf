terraform {
  required_version = ">= 1.6.0, < 2.0.0"
  # Backend values are injected by the protected CI environment at init time.
  # Keeping this block empty prevents credentials or environment-specific state
  # locations from entering source control.
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
