variable "aws_region" {
  description = "AWS region for the PostgreSQL instance."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "db_identifier" {
  type    = string
  default = "streamshield-bi"
}

variable "db_name" {
  type    = string
  default = "streamshield"
}

variable "db_username" {
  type    = string
  default = "streamshield_admin"
}

variable "db_instance_class" {
  description = "Choose a size supported in the selected region and account."
  type        = string
  default     = "db.t4g.micro"
}

variable "postgres_engine_version" {
  description = "Set to a PostgreSQL major version available in the selected AWS region."
  type        = string
  default     = "16.15"
}

variable "allowed_client_cidrs" {
  description = "Static IPv4 CIDRs for the Power BI gateway host and admin workstation. Never use 0.0.0.0/0."
  type        = list(string)
  validation {
    condition     = length(var.allowed_client_cidrs) > 0 && alltrue([for cidr in var.allowed_client_cidrs : cidr != "0.0.0.0/0"])
    error_message = "Add at least one trusted static CIDR and do not expose PostgreSQL to the internet."
  }
}
