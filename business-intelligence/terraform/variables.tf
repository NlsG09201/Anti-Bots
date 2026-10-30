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
  description = "Static IPv4 /32 host CIDRs for the Power BI gateway and admin workstation."
  type        = list(string)
  validation {
    condition = length(var.allowed_client_cidrs) > 0 && alltrue([
      for cidr in var.allowed_client_cidrs : can(cidrnetmask(cidr)) && endswith(cidr, "/32")
    ])
    error_message = "Provide at least one valid static IPv4 /32 address for each trusted client."
  }
}
