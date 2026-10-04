output "resource_group_name" { value = module.aks.resource_group_name }
output "cluster_id" { value = module.aks.cluster_id }
output "oidc_issuer_url" { value = module.aks.oidc_issuer_url }
output "postgres_fqdn" { value = module.aks.postgres_fqdn }
output "dns_zone_id" { value = module.aks.dns_zone_id }
output "key_vault_id" { value = module.aks.key_vault_id }
output "workload_identity_client_ids" { value = module.aks.workload_identity_client_ids }
