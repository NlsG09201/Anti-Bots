output "database_endpoint" {
  value       = aws_db_instance.bi.address
  description = "Use this host in DATABASE_URL and Power BI Desktop; store credentials as secrets."
}

output "database_port" {
  value = aws_db_instance.bi.port
}

output "database_name" {
  value = aws_db_instance.bi.db_name
}

output "master_user_secret_arn" {
  value       = aws_db_instance.bi.master_user_secret[0].secret_arn
  description = "AWS Secrets Manager ARN for the managed master password."
}
