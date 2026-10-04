variable "name" {
  type = string
}
variable "kubernetes_version" {
  type    = string
  default = "1.31"
}
variable "vpc_id" {
  type = string
}
variable "private_subnet_ids" {
  type = list(string)
}
variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}
variable "node_min_size" {
  type    = number
  default = 2
}
variable "node_max_size" {
  type    = number
  default = 6
}
variable "node_desired_size" {
  type    = number
  default = 2
}
variable "kms_key_arn" {
  type    = string
  default = null
}
variable "tags" {
  type = map(string)
  default = {
  }
}
