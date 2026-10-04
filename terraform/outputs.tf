output "project_id" {
  value = var.project_id
}
output "network_name" {
  value = google_compute_network.vpc.name
}
output "gke_cluster_name" {
  value = google_container_cluster.gke.name
}
output "gke_endpoint" {
  value     = google_container_cluster.gke.endpoint
  sensitive = true
}
output "sql_instance_name" {
  value = google_sql_database_instance.postgres.name
}
output "sql_private_ip" {
  value = try(google_sql_database_instance.postgres.private_ip_address, null)
}
output "dns_zone_name" {
  value = google_dns_managed_zone.platform.name
}
output "secret_resource_name" {
  value = google_secret_manager_secret.database.name
}
output "kms_key_name" {
  value = google_kms_crypto_key.secrets.name
}
output "cloud_armor_policy_name" {
  value = google_compute_security_policy.cloud_armor.name
}
output "workload_identity_service_accounts" {
  value = { for k, v in local.workload_identities : k => v.sa }
}
output "argo_bootstrap_boundary" {
  value = "Terraform creates cluster/IAM hooks only; Argo installs and reconciles workloads from GitOps."
}
output "backup_targets" {
  value = {
    rpo_hours             = var.rpo_hours
    rto_hours             = var.rto_hours
    sql_pitr              = true
    sql_backup_start_time = var.sql_backup_start_time
  }
}
