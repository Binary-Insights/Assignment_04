aws_region = "us-east-1"
instance_type = "t3.medium"

# Restrict SSH to your IP for security (replace with your actual IP)
allowed_ssh_cidr = ["0.0.0.0/0"]

# These will be provided during terraform apply or via environment
# ecr_registry = "123456789012.dkr.ecr.us-east-1.amazonaws.com"
# app_image = "assignment-04:latest"
