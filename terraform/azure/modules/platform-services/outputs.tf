output "postgres_server_id" { value = azurerm_postgresql_flexible_server.this.id }
output "postgres_fqdn" { value = azurerm_postgresql_flexible_server.this.fqdn }
output "dns_zone_id" { value = azurerm_dns_zone.public.id }
output "key_vault_id" { value = azurerm_key_vault.this.id }
output "cluster_disk_key_id" { value = azurerm_key_vault_key.cluster_disk.id }
output "log_workspace_id" { value = azurerm_log_analytics_workspace.platform.id }
