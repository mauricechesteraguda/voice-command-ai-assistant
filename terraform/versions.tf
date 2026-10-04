terraform {
  required_version = ">= 1.6.0, < 2.0.0"
  backend "gcs" {
    bucket = "REQUIRED_TF_STATE_BUCKET"
    prefix = "voice-platform"
  }

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
