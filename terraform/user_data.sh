#!/bin/bash
set -e

# Update system
apt-get update
apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Start Docker
systemctl start docker
systemctl enable docker

# Add ubuntu user to docker group
usermod -aG docker ubuntu

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install AWS CLI
apt-get install -y awscli

# Create app directory
mkdir -p /opt/assignment-04
cd /opt/assignment-04

# Log Docker daemon output
mkdir -p /var/log/assignment-04
cat > /etc/systemd/system/assignment-04.service <<EOF
[Unit]
Description=Assignment 04 Docker Compose
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/assignment-04
User=ubuntu
ExecStart=/usr/local/bin/docker-compose -f docker-compose.yml up
ExecStop=/usr/local/bin/docker-compose -f docker-compose.yml down
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service (will fail initially, but that's OK - wait for deployment)
systemctl daemon-reload
systemctl enable assignment-04

# Log completion
echo "Docker and Docker Compose installed successfully" > /var/log/assignment-04/setup.log
