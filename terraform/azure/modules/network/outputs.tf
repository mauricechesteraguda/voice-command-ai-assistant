output "vnet_id" { value = azurerm_virtual_network.this.id }
output "aks_subnet_id" { value = azurerm_subnet.aks.id }
output "postgres_subnet_id" { value = azurerm_subnet.postgres.id }
output "private_endpoints_subnet_id" { value = azurerm_subnet.private_endpoints.id }
