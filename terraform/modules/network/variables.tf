variable "name" {
  type = string
}
variable "region" {
  type = string
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "availability_zones" {
  type    = list(string)
  default = []
}
variable "enable_flow_logs" {
  type    = bool
  default = true
}
variable "tags" {
  type = map(string)
  default = {
  }
}
