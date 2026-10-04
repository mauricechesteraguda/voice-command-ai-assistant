resource "azurerm_user_assigned_identity" "aks" {
  name                = "${var.name}-aks-identity"
  location            = var.location
  resource_group_name = var.resource_group_name
}

resource "azurerm_disk_encryption_set" "this" {
  name                = "${var.name}-des"
  location            = var.location
  resource_group_name = var.resource_group_name
  key_vault_key_id    = var.disk_encryption_set_key_id
  identity { type = "SystemAssigned" }
}

resource "azurerm_role_assignment" "des_crypto" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Crypto Service Encryption User"
  principal_id         = azurerm_disk_encryption_set.this.identity[0].principal_id
}

locals {
  workload_identities = {
    argo             = { namespace = "argocd", service_account = "argocd-server" }
    external_secrets = { namespace = "external-secrets", service_account = "external-secrets" }
    external_dns     = { namespace = "external-dns", service_account = "external-dns" }
    cert_manager     = { namespace = "cert-manager", service_account = "cert-manager" }
  }
}

resource "azurerm_user_assigned_identity" "workload" {
  for_each            = local.workload_identities
  name                = "${var.name}-${each.key}-wi"
  location            = var.location
  resource_group_name = var.resource_group_name
}

resource "azurerm_federated_identity_credential" "workload" {
  for_each            = local.workload_identities
  name                = "${each.key}-service-account"
  resource_group_name = var.resource_group_name
  parent_id           = azurerm_user_assigned_identity.workload[each.key].id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.this.oidc_issuer_url
  subject             = "system:serviceaccount:${each.value.namespace}:${each.value.service_account}"
}

resource "azurerm_role_assignment" "external_dns_zone" {
  for_each             = toset(["external_dns", "cert_manager"])
  scope                = var.dns_zone_id
  role_definition_name = "DNS Zone Contributor"
  principal_id         = azurerm_user_assigned_identity.workload[each.key].principal_id
}

resource "azurerm_role_assignment" "eso_vault" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.workload["external_secrets"].principal_id
}

resource "azurerm_kubernetes_cluster" "this" {
  name                      = "${var.name}-aks"
  location                  = var.location
  resource_group_name       = var.resource_group_name
  dns_prefix                = var.name
  kubernetes_version        = var.kubernetes_version
  private_cluster_enabled   = true
  workload_identity_enabled = true
  oidc_issuer_enabled       = true
  sku_tier                  = "Standard"
  azure_policy_enabled      = true
  local_account_disabled    = true
  disk_encryption_set_id    = azurerm_disk_encryption_set.this.id

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks.id]
  }
  default_node_pool {
    name                 = "system"
    vm_size              = "Standard_D4ds_v5"
    vnet_subnet_id       = var.aks_subnet_id
    auto_scaling_enabled = true
    min_count            = var.system_node_min_count
    max_count            = var.system_node_max_count
    os_disk_type         = "Ephemeral"
  }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "azure"
    outbound_type       = "userAssignedNATGateway"
    load_balancer_sku   = "standard"
  }
  dynamic "oms_agent" {
    for_each = var.log_workspace_id == null ? [] : [var.log_workspace_id]
    content { log_analytics_workspace_id = oms_agent.value }
  }
  key_vault_secrets_provider { secret_rotation_enabled = true }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_kubernetes_cluster_node_pool" "user" {
  name                  = "user"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.this.id
  vm_size               = "Standard_D4ds_v5"
  vnet_subnet_id        = var.aks_subnet_id
  auto_scaling_enabled  = true
  min_count             = var.user_node_min_count
  max_count             = var.user_node_max_count
  mode                  = "User"
  node_labels           = { workload = "application" }
}
