output "vpc_id" {
  value = module.network.vpc_id
}
output "cluster_name" {
  value = module.cluster.cluster_name
}
output "cluster_endpoint" {
  value     = module.cluster.cluster_endpoint
  sensitive = true
}
output "database_endpoint" {
  value = module.services.database_endpoint
}
output "database_secret_arn" {
  value = module.services.database_secret_arn
}
output "workload_role_arns" {
  value = module.services.workload_role_arns
}
output "gateway_waf_arn" {
  value = module.services.gateway_waf_arn
}
output "backup_vault_name" {
  value = module.services.backup_vault_name
}
