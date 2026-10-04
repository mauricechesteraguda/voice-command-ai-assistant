variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "aks_subnet_id" { type = string }
variable "disk_encryption_set_key_id" { type = string }
variable "key_vault_id" { type = string }
variable "dns_zone_id" { type = string }
variable "kubernetes_version" {
  type    = string
  default = null
}
variable "system_node_min_count" { type = number }
variable "system_node_max_count" { type = number }
variable "user_node_min_count" { type = number }
variable "user_node_max_count" { type = number }
variable "log_workspace_id" {
  type    = string
  default = null
}
