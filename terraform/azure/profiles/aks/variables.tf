variable "name" {
  type    = string
  default = "voice"
}
variable "location" {
  type    = string
  default = "eastus"
}
variable "dns_zone_name" { type = string }
variable "postgres_admin_login" {
  type      = string
  sensitive = true
}
variable "postgres_admin_password" {
  type      = string
  sensitive = true
}
variable "key_vault_admin_object_ids" {
  type    = set(string)
  default = []
}
variable "system_node_min_count" {
  type    = number
  default = 2
}
variable "system_node_max_count" {
  type    = number
  default = 5
}
variable "user_node_min_count" {
  type    = number
  default = 2
}
variable "user_node_max_count" {
  type    = number
  default = 10
}
variable "log_workspace_id" {
  type    = string
  default = null
}
variable "prevent_destroy" {
  type    = bool
  default = true
}
