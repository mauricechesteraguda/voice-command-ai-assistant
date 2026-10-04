terraform {
  required_version = "~> 1.16.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "4.44.0"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "this" {
  name     = "${var.name}-rg"
  location = var.location
  tags     = { managed_by = "terraform", workload = "voice-platform" }
  lifecycle { prevent_destroy = true }
}

module "network" {
  source                        = "../../../modules/network"
  name                          = var.name
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  vnet_cidr                     = "10.40.0.0/16"
  aks_subnet_cidr               = "10.40.0.0/20"
  postgres_subnet_cidr          = "10.40.16.0/24"
  private_endpoints_subnet_cidr = "10.40.17.0/24"
}

module "platform_services" {
  source                     = "../../../modules/platform-services"
  name                       = var.name
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  vnet_id                    = module.network.vnet_id
  postgres_subnet_id         = module.network.postgres_subnet_id
  postgres_admin_login       = var.postgres_admin_login
  postgres_admin_password    = var.postgres_admin_password
  dns_zone_name              = var.dns_zone_name
  key_vault_admin_object_ids = var.key_vault_admin_object_ids
}

module "cluster" {
  source                     = "../../../modules/cluster"
  name                       = var.name
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  aks_subnet_id              = module.network.aks_subnet_id
  disk_encryption_set_key_id = module.platform_services.cluster_disk_key_id
  key_vault_id               = module.platform_services.key_vault_id
  dns_zone_id                = module.platform_services.dns_zone_id
  system_node_min_count      = var.system_node_min_count
  system_node_max_count      = var.system_node_max_count
  user_node_min_count        = var.user_node_min_count
  user_node_max_count        = var.user_node_max_count
  log_workspace_id           = module.platform_services.log_workspace_id
  depends_on                 = [module.platform_services]
}
