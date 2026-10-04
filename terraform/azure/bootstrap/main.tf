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

variable "location" {
  type    = string
  default = "eastus"
}

variable "state_resource_group_name" {
  type    = string
  default = "platform-tfstate-rg"
}

variable "state_storage_account_name" {
  type = string
}

resource "azurerm_resource_group" "state" {
  name     = var.state_resource_group_name
  location = var.location
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_account" "state" {
  name                              = var.state_storage_account_name
  resource_group_name               = azurerm_resource_group.state.name
  location                          = azurerm_resource_group.state.location
  account_tier                      = "Standard"
  account_replication_type          = "ZRS"
  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  shared_access_key_enabled         = false
  public_network_access_enabled     = false
  infrastructure_encryption_enabled = true
  blob_properties {
    versioning_enabled  = true
    change_feed_enabled = true
  }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_container" "terraform" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

output "backend_storage_account" { value = azurerm_storage_account.state.name }
output "backend_container" { value = azurerm_storage_container.terraform.name }
