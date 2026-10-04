resource "azurerm_private_dns_zone" "postgres" {
  name                = "${var.name}.postgres.database.azure.com"
  resource_group_name = var.resource_group_name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "${var.name}-postgres-link"
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = var.vnet_id
  resource_group_name   = var.resource_group_name
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                         = "${var.name}-postgres"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  version                      = "16"
  delegated_subnet_id          = var.postgres_subnet_id
  private_dns_zone_id          = azurerm_private_dns_zone.postgres.id
  administrator_login          = var.postgres_admin_login
  administrator_password       = var.postgres_admin_password
  sku_name                     = var.postgres_sku_name
  storage_mb                   = 32768
  backup_retention_days        = var.postgres_backup_retention_days
  geo_redundant_backup_enabled = true
  zone                         = "1"
  identity { type = "SystemAssigned" }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = "app"
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_dns_zone" "public" {
  name                = var.dns_zone_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_key_vault" "this" {
  name                          = substr(replace("${var.name}-vault", "-", ""), 0, 24)
  location                      = var.location
  resource_group_name           = var.resource_group_name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  enable_rbac_authorization     = true
  public_network_access_enabled = false
  lifecycle { prevent_destroy = true }
}

data "azurerm_client_config" "current" {}

resource "azurerm_log_analytics_workspace" "platform" {
  name                = "${var.name}-logs"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_role_assignment" "key_vault_admin" {
  for_each             = var.key_vault_admin_object_ids
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = each.value
}

resource "azurerm_key_vault_key" "cluster_disk" {
  name         = "cluster-disk-encryption"
  key_vault_id = azurerm_key_vault.this.id
  key_type     = "RSA"
  key_size     = 4096
  key_opts     = ["decrypt", "encrypt", "sign", "unwrapKey", "verify", "wrapKey"]
  depends_on   = [azurerm_role_assignment.key_vault_admin]
}
