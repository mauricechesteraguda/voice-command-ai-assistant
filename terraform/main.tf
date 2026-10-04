locals {
  prefix = "${var.name}-${var.environment}"
  services = toset([
    "container.googleapis.com", "compute.googleapis.com", "sqladmin.googleapis.com",
    "dns.googleapis.com", "secretmanager.googleapis.com", "cloudkms.googleapis.com",
    "logging.googleapis.com", "monitoring.googleapis.com"
  ])
}

resource "google_project_service" "platform" {
  for_each           = local.services
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_billing_budget" "platform" {
  count           = var.billing_account_id == "" ? 0 : 1
  billing_account = var.billing_account_id
  display_name    = "${local.prefix}-monthly"
  budget_filter {
    projects = ["projects/${var.project_id}"]
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }
}

resource "google_compute_network" "vpc" {
  name                    = "${local.prefix}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "gke" {
  name                     = "${local.prefix}-gke"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.network_cidr
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }
}

resource "google_compute_router" "nat" {
  name    = "${local.prefix}-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${local.prefix}-nat"
  router                             = google_compute_router.nat.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
  subnetwork {
    name                    = google_compute_subnetwork.gke.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}

resource "google_container_cluster" "gke" {
  name                     = local.prefix
  location                 = var.region
  network                  = google_compute_network.vpc.name
  subnetwork               = google_compute_subnetwork.gke.name
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = true
  networking_mode          = "VPC_NATIVE"

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }
  workload_identity_config { workload_pool = "${var.project_id}.svc.id.goog" }
  release_channel { channel = var.gke_release_channel }
  addons_config {
    http_load_balancing { disabled = false }
    horizontal_pod_autoscaling { disabled = false }
    gce_persistent_disk_csi_driver_config { enabled = true }
  }
  resource_labels = var.labels
  depends_on      = [google_project_service.platform]
}

resource "google_container_node_pool" "general" {
  name       = "general"
  cluster    = google_container_cluster.gke.name
  location   = var.region
  node_count = var.node_min_count
  autoscaling {
    min_node_count = var.node_min_count
    max_node_count = var.node_max_count
  }
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  node_config {
    machine_type = var.node_machine_type
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/servicecontrol",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/trace.append",
    ]
    service_account = google_service_account.nodes.email
    workload_metadata_config { mode = "GKE_METADATA" }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
}

resource "google_service_account" "nodes" { account_id = "${local.prefix}-nodes" }

resource "google_sql_database_instance" "postgres" {
  name                = "${local.prefix}-postgres"
  database_version    = "POSTGRES_15"
  region              = var.region
  deletion_protection = true
  settings {
    tier              = var.sql_tier
    availability_type = "REGIONAL"
    disk_type         = "PD_SSD"
    disk_autoresize   = true
    backup_configuration {
      enabled                        = true
      start_time                     = var.sql_backup_start_time
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
    }
    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.vpc.id
      enable_private_path_for_google_cloud_services = true
    }
    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
      record_client_address   = false
    }
  }
  depends_on = [google_project_service.platform]
}

resource "google_sql_database" "app" {
  name     = "application"
  instance = google_sql_database_instance.postgres.name
}

resource "google_dns_managed_zone" "platform" {
  name        = replace(local.prefix, "-", "")
  dns_name    = var.dns_name
  description = "Managed by Terraform; records are provider-native and secret-free."
}
resource "google_dns_record_set" "gateway" {
  count        = var.enable_dns_record && var.gateway_ip != "" ? 1 : 0
  name         = var.dns_name
  managed_zone = google_dns_managed_zone.platform.name
  type         = "A"
  ttl          = 300
  rrdatas      = [var.gateway_ip]
}

resource "google_kms_key_ring" "platform" {
  name     = "${local.prefix}-ring"
  location = var.region
}
resource "google_kms_crypto_key" "secrets" {
  name            = "${local.prefix}-secrets"
  key_ring        = google_kms_key_ring.platform.id
  rotation_period = "7776000s"
  lifecycle { prevent_destroy = true }
}
resource "google_secret_manager_secret" "database" {
  secret_id = "${local.prefix}/database"
  replication {
    auto {}
  }
  lifecycle { prevent_destroy = true }
}

resource "google_compute_security_policy" "cloud_armor" {
  name        = "${local.prefix}-armor"
  description = "Hook for the GKE Gateway external HTTP(S) load balancer."
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
  }
}

resource "google_service_account" "argo" { account_id = "${local.prefix}-argo" }
resource "google_service_account" "eso" { account_id = "${local.prefix}-eso" }
resource "google_service_account" "externaldns" { account_id = "${local.prefix}-externaldns" }
resource "google_service_account" "cert_manager" { account_id = "${local.prefix}-cert-manager" }

locals {
  workload_identities = {
    argo         = { sa = google_service_account.argo.name, ns = var.argo_namespace, ksa = "argocd-controller" }
    eso          = { sa = google_service_account.eso.name, ns = var.eso_namespace, ksa = "external-secrets" }
    externaldns  = { sa = google_service_account.externaldns.name, ns = var.externaldns_namespace, ksa = "external-dns" }
    cert_manager = { sa = google_service_account.cert_manager.name, ns = var.cert_manager_namespace, ksa = "cert-manager" }
  }
}
resource "google_service_account_iam_member" "workload_identity" {
  for_each           = local.workload_identities
  service_account_id = each.value.sa
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${each.value.ns}/${each.value.ksa}]"
}

resource "google_project_iam_audit_config" "platform" {
  project = var.project_id
  service = "allServices"
  audit_log_config { log_type = "ADMIN_READ" }
  audit_log_config { log_type = "DATA_READ" }
  audit_log_config { log_type = "DATA_WRITE" }
}

resource "google_logging_project_sink" "platform" {
  count       = var.log_bucket_name == "" ? 0 : 1
  name        = "${local.prefix}-audit"
  destination = "logging.googleapis.com/projects/${var.project_id}/locations/global/buckets/${var.log_bucket_name}"
  filter      = "log_id(\"cloudaudit.googleapis.com\") OR resource.type=\"k8s_cluster\""
}
