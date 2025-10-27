variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "allowed_ssh_cidr" {
  description = "CIDR blocks allowed for SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"] # Change this to your IP for security
}

variable "ecr_registry" {
  description = "ECR registry URL"
  type        = string
  default     = ""
}

variable "app_image" {
  description = "Docker image name and tag"
  type        = string
  default     = "assignment-04:latest"
}

variable "environment_variables" {
  description = "Environment variables for the Docker container"
  type        = map(string)
  default = {
    PYTHONUNBUFFERED = "1"
  }
  sensitive = true
}
