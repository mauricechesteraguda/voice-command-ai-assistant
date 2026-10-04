output "resource_group_name" { value = azurerm_resource_group.this.name }
output "cluster_id" { value = module.cluster.cluster_id }
output "oidc_issuer_url" { value = module.cluster.oidc_issuer_url }
output "postgres_fqdn" { value = module.platform_services.postgres_fqdn }
output "dns_zone_id" { value = module.platform_services.dns_zone_id }
output "key_vault_id" { value = module.platform_services.key_vault_id }
output "workload_identity_client_ids" { value = module.cluster.workload_identity_client_ids }
