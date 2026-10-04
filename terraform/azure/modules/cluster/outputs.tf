output "cluster_id" { value = azurerm_kubernetes_cluster.this.id }
output "oidc_issuer_url" { value = azurerm_kubernetes_cluster.this.oidc_issuer_url }
output "kubelet_identity_object_id" { value = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id }
output "workload_identity_client_ids" { value = { for name, identity in azurerm_user_assigned_identity.workload : name => identity.client_id } }
