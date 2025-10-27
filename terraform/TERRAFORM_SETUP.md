# Terraform + GitHub Actions CI/CD Setup

This directory contains Terraform scripts to automate deployment of the Assignment 04 app to AWS EC2 with GitHub Actions CI/CD.

## Architecture

```
GitHub Repository
    ↓ (on push to main)
GitHub Actions
    ├─ Build Docker images (API + Streamlit)
    ├─ Push to AWS ECR
    └─ Deploy to EC2 instance (via SSH)
        ↓
    EC2 Instance (Ubuntu 22.04)
        ├─ Docker Engine
        ├─ FastAPI service (port 8000)
        └─ Streamlit service (port 8501)
```

## Prerequisites

1. **Ensure AWS CLI is configured**
   ```bash
   aws sts get-caller-identity
   ```
   This should return your current AWS user/account info. If it fails, configure with:
   ```bash
   aws configure
   ```
   You'll be prompted for:
   - AWS Access Key ID
   - AWS Secret Access Key
   - Default region (e.g., `us-east-1`)
   - Default output format (e.g., `json`)

2. **AWS Account** with appropriate permissions (EC2, ECR, IAM, CloudWatch)
3. **Terraform** installed locally (`>= 1.0`)
4. **GitHub repository** with this code
5. **AWS IAM User/Role** for GitHub Actions (OIDC recommended)

## Step 1: Set up AWS IAM for GitHub Actions (OIDC)

Using GitHub's OpenID Connect (OIDC) is more secure than storing AWS credentials.

### Create IAM Role for GitHub Actions

Run this AWS CLI command or create manually in AWS Console:

```bash
aws iam create-role \
  --role-name GitHubActionsRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Federated": "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
        },
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {
          "StringLike": {
            "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_ORG/YOUR_REPO:*"
          }
        }
      }
    ]
  }'
```

### Attach Policies

```bash
# ECR permissions
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

# EC2 read permissions (to find instance)
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess

# Custom policy for deploying to EC2
aws iam put-role-policy \
  --role-name GitHubActionsRole \
  --policy-name GitHubActionsEC2Deploy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "ec2:DescribeInstances"
        ],
        "Resource": "*"
      }
    ]
  }'
```

## Step 2: Configure GitHub Secrets

Add these secrets to your GitHub repository settings:

1. **AWS_ROLE_TO_ASSUME**: ARN of the IAM role created above
   ```
   arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/GitHubActionsRole
   ```

2. **AWS_ACCOUNT_ID**: Your AWS account ID (12 digits)

3. **OPENAI_API_KEY**: Your OpenAI API key (starts with `sk-...`)

4. **EC2_SSH_KEY**: Private SSH key for accessing EC2 (for initial setup)
   ```bash
   # Generate a key pair (if you don't have one)
   ssh-keygen -t rsa -b 4096 -f assignment-04-key -N ""
   
   # Copy the private key content to GitHub secret
   cat assignment-04-key
   ```

## Step 3: Deploy Infrastructure with Terraform

### Initialize Terraform

```bash
cd terraform
terraform init
```

### Plan the deployment

```bash
# Customize terraform.tfvars before this
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars to set your preferred AWS region, instance type, etc.

terraform plan -out=tfplan
```

### Apply the configuration

```bash
terraform apply tfplan
```

**Output will show:**
- EC2 instance ID and public IP
- FastAPI URL
- Streamlit URL
- ECR repository URL

Example output:
```
fastapi_url = "http://203.0.113.42:8000"
streamlit_url = "http://203.0.113.42:8501"
instance_public_ip = "203.0.113.42"
ecr_repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/assignment-04"
```

## Step 4: Trigger CI/CD Pipeline

Push code to the main branch to trigger the GitHub Actions workflow:

```bash
git add .
git commit -m "Deploy with Terraform and CI/CD"
git push origin main
```

Monitor the workflow:
1. Go to GitHub → Actions
2. Watch the build-and-push and deploy jobs
3. Check EC2 instance for running containers

## Accessing the Application

After successful deployment:

- **FastAPI**: http://YOUR_EC2_IP:8000
- **Streamlit**: http://YOUR_EC2_IP:8501
- **FastAPI Health**: http://YOUR_EC2_IP:8000/health

## Manual SSH Access to EC2

```bash
# Set your EC2 private key permissions
chmod 600 assignment-04-key

# SSH into the instance
ssh -i assignment-04-key ubuntu@YOUR_EC2_PUBLIC_IP

# Check container logs
docker-compose -f /opt/assignment-04/docker-compose.yml logs -f

# Restart services
docker-compose -f /opt/assignment-04/docker-compose.yml restart
```

## Cleanup

To destroy all AWS resources:

```bash
cd terraform
terraform destroy
```

This will:
- Terminate the EC2 instance
- Remove security groups
- Delete ECR repository
- Remove IAM roles
- Delete CloudWatch log groups

## Troubleshooting

### GitHub Actions workflow fails

1. Check GitHub Actions logs: GitHub → Actions → Failed workflow
2. Verify AWS_ROLE_TO_ASSUME and AWS_ACCOUNT_ID secrets are correct
3. Ensure IAM role has proper permissions

### EC2 instance creation fails

```bash
terraform plan
# Check for errors, then retry
terraform apply
```

### Docker services not starting on EC2

```bash
# SSH into instance
ssh -i assignment-04-key ubuntu@YOUR_IP

# Check Docker status
systemctl status docker

# Check service status
systemctl status assignment-04

# View logs
journalctl -u assignment-04 -f
```

### OPENAI_API_KEY not accessible in Streamlit

1. Verify secret is set in GitHub
2. Check CloudWatch logs: `/assignment-04/docker`
3. SSH into EC2 and verify env var: `docker exec assignment-04-streamlit env | grep OPENAI`

## Security Best Practices

1. **Restrict SSH CIDR**: Update `allowed_ssh_cidr` in `terraform.tfvars` to your IP
2. **Use OIDC**: Prefer OIDC over hardcoded AWS credentials
3. **Rotate SSH keys**: Regularly rotate the EC2_SSH_KEY secret
4. **Monitor CloudWatch**: Set up alarms for unusual activity
5. **Use NAT gateway**: For production, run EC2 in private subnet with NAT gateway
6. **Enable VPC Flow Logs**: For production deployments
7. **Use AWS Secrets Manager**: Store OPENAI_API_KEY in Secrets Manager, not GitHub

## Production Considerations

For production deployments:

1. **Use RDS** for persistent data (if needed)
2. **Add Application Load Balancer (ALB)** for high availability
3. **Use Auto Scaling Groups** for scaling
4. **Enable AWS WAF** for DDoS protection
5. **Use Route 53** for custom domains
6. **Enable CloudFront** for CDN
7. **Set up automated backups** and disaster recovery
8. **Use VPC endpoints** for private AWS service access
9. **Enable GuardDuty** for threat detection
10. **Implement proper tagging strategy** for cost allocation

## Further Customization

- Modify `instance_type` in `terraform.tfvars` (e.g., `t3.large` for higher capacity)
- Add RDS database by extending `main.tf`
- Add Application Load Balancer (ALB) for multiple instances
- Configure custom domain with Route 53
- Add CloudFront for caching and CDN

For questions or issues, refer to:
- Terraform Docs: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- GitHub Actions: https://docs.github.com/en/actions
- AWS Documentation: https://docs.aws.amazon.com/
