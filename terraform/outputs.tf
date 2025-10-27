output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "instance_public_ip" {
  description = "EC2 instance public IP"
  value       = aws_instance.app.public_ip
}

output "instance_public_dns" {
  description = "EC2 instance public DNS"
  value       = aws_instance.app.public_dns
}

output "fastapi_url" {
  description = "FastAPI endpoint URL"
  value       = "http://${aws_instance.app.public_ip}:8000"
}

output "streamlit_url" {
  description = "Streamlit endpoint URL"
  value       = "http://${aws_instance.app.public_ip}:8501"
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.app_sg.id
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.app_repo.repository_url
}

output "ecr_registry" {
  description = "ECR registry URI"
  value       = aws_ecr_repository.app_repo.registry_id
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.app_logs.name
}
