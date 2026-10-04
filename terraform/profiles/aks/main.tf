// Compatibility entry point for callers using the original provider-neutral path.
// The Azure implementation remains the sole owner of Azure resources and provider
// configuration; this wrapper only forwards the public profile contract.
module "aks" {
  source = "../../azure/profiles/aks"

  name                       = var.name
  location                   = var.location
  dns_zone_name              = var.dns_zone_name
  postgres_admin_login       = var.postgres_admin_login
  postgres_admin_password    = var.postgres_admin_password
  key_vault_admin_object_ids = var.key_vault_admin_object_ids
  system_node_min_count      = var.system_node_min_count
  system_node_max_count      = var.system_node_max_count
  user_node_min_count        = var.user_node_min_count
  user_node_max_count        = var.user_node_max_count
  log_workspace_id           = var.log_workspace_id
  prevent_destroy            = var.prevent_destroy
}
