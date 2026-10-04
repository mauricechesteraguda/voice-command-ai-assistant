variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "postgres_subnet_id" { type = string }
variable "vnet_id" { type = string }
variable "postgres_admin_login" {
  type      = string
  sensitive = true
}
variable "postgres_admin_password" {
  type      = string
  sensitive = true
}
variable "postgres_sku_name" {
  type    = string
  default = "B_Standard_B1ms"
}
variable "postgres_backup_retention_days" {
  type    = number
  default = 7
}
variable "dns_zone_name" { type = string }
variable "key_vault_admin_object_ids" {
  type    = set(string)
  default = []
}
