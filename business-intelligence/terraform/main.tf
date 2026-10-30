terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_db_subnet_group" "bi" {
  name       = "streamshield-bi"
  subnet_ids = data.aws_subnets.default.ids
  tags       = { Project = "StreamShield-BI" }
}

resource "aws_security_group" "postgres" {
  name        = "streamshield-bi-postgres"
  description = "PostgreSQL access from explicitly allowed Power BI gateway/operator IPs"
  vpc_id      = data.aws_vpc.default.id

  dynamic "ingress" {
    for_each = var.allowed_client_cidrs
    content {
      description = "PostgreSQL from approved client or gateway"
      from_port   = 5432
      to_port     = 5432
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  tags = { Project = "StreamShield-BI" }
}

resource "aws_db_instance" "bi" {
  identifier                          = var.db_identifier
  engine                              = "postgres"
  engine_version                      = var.postgres_engine_version
  instance_class                      = var.db_instance_class
  allocated_storage                   = 20
  max_allocated_storage               = 100
  storage_type                        = "gp3"
  storage_encrypted                   = true
  db_name                             = var.db_name
  username                            = var.db_username
  manage_master_user_password         = true
  port                                = 5432
  publicly_accessible                 = true
  db_subnet_group_name                = aws_db_subnet_group.bi.name
  vpc_security_group_ids              = [aws_security_group.postgres.id]
  backup_retention_period             = 7
  copy_tags_to_snapshot               = true
  auto_minor_version_upgrade          = true
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${var.db_identifier}-final"
  apply_immediately                   = false
  iam_database_authentication_enabled = true

  tags = {
    Project     = "StreamShield-BI"
    Environment = var.environment
  }
}
