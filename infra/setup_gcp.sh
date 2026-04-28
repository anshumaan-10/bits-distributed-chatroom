#!/bin/bash
# =========================================================================
# setup_gcp.sh - Create 3 GCP Compute Engine VMs for Distributed Chat Room
# =========================================================================
# Course: CCZG 526 - Distributed Computing
# Group : 8
#
# This script provisions 3 VM instances on Google Cloud Platform:
#   - chatroom-server  (Node 3) : Hosts the shared chat file
#   - chatroom-node1   (Node 1) : User node (Anshumaan)
#   - chatroom-node2   (Node 2) : User node (Sekhar)
#
# All VMs are created in the same zone/VPC so they can communicate
# via internal IPs without firewall issues.
#
# Usage:
#   chmod +x setup_gcp.sh
#   ./setup_gcp.sh
# =========================================================================

set -e

# configuration
PROJECT_ID="avian-voice-433417-d5"
ZONE="asia-south1-a"
MACHINE_TYPE="e2-micro"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

# VM names
SERVER_VM="chatroom-server"
NODE1_VM="chatroom-node1"
NODE2_VM="chatroom-node2"

# firewall rule name for our chat room ports
FIREWALL_RULE="allow-chatroom-ports"

echo "============================================="
echo " Distributed Chat Room - GCP Setup"
echo " Project: ${PROJECT_ID}"
echo " Zone:    ${ZONE}"
echo "============================================="

# set the project
gcloud config set project ${PROJECT_ID}

# ---- Create firewall rule ----
echo ""
echo "[1/5] Creating firewall rule for chat room ports (5000, 6001, 6002)..."
gcloud compute firewall-rules create ${FIREWALL_RULE} \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:5000,tcp:6001,tcp:6002 \
    --source-ranges=10.0.0.0/8 \
    --target-tags=chatroom \
    --description="Allow internal traffic for distributed chat room" \
    2>/dev/null || echo "  (Firewall rule already exists, skipping)"

# ---- Create VMs ----
echo ""
echo "[2/5] Creating VM: ${SERVER_VM} (File Server - Node 3)..."
gcloud compute instances create ${SERVER_VM} \
    --zone=${ZONE} \
    --machine-type=${MACHINE_TYPE} \
    --image-family=${IMAGE_FAMILY} \
    --image-project=${IMAGE_PROJECT} \
    --tags=chatroom \
    --metadata=startup-script='#!/bin/bash
apt-get update -qq
apt-get install -y -qq python3 python3-pip > /dev/null 2>&1' \
    2>/dev/null || echo "  (VM already exists, skipping)"

echo ""
echo "[3/5] Creating VM: ${NODE1_VM} (User Node 1 - Anshumaan)..."
gcloud compute instances create ${NODE1_VM} \
    --zone=${ZONE} \
    --machine-type=${MACHINE_TYPE} \
    --image-family=${IMAGE_FAMILY} \
    --image-project=${IMAGE_PROJECT} \
    --tags=chatroom \
    --metadata=startup-script='#!/bin/bash
apt-get update -qq
apt-get install -y -qq python3 python3-pip > /dev/null 2>&1' \
    2>/dev/null || echo "  (VM already exists, skipping)"

echo ""
echo "[4/5] Creating VM: ${NODE2_VM} (User Node 2 - Sekhar)..."
gcloud compute instances create ${NODE2_VM} \
    --zone=${ZONE} \
    --machine-type=${MACHINE_TYPE} \
    --image-family=${IMAGE_FAMILY} \
    --image-project=${IMAGE_PROJECT} \
    --tags=chatroom \
    --metadata=startup-script='#!/bin/bash
apt-get update -qq
apt-get install -y -qq python3 python3-pip > /dev/null 2>&1' \
    2>/dev/null || echo "  (VM already exists, skipping)"

# ---- Fetch internal IPs ----
echo ""
echo "[5/5] Fetching internal IPs..."
SERVER_IP=$(gcloud compute instances describe ${SERVER_VM} --zone=${ZONE} \
    --format='get(networkInterfaces[0].networkIP)')
NODE1_IP=$(gcloud compute instances describe ${NODE1_VM} --zone=${ZONE} \
    --format='get(networkInterfaces[0].networkIP)')
NODE2_IP=$(gcloud compute instances describe ${NODE2_VM} --zone=${ZONE} \
    --format='get(networkInterfaces[0].networkIP)')

echo ""
echo "============================================="
echo " VM Internal IPs:"
echo "   ${SERVER_VM}: ${SERVER_IP}"
echo "   ${NODE1_VM}:  ${NODE1_IP}"
echo "   ${NODE2_VM}:  ${NODE2_IP}"
echo "============================================="

# ---- Generate config.json with actual IPs ----
CONFIG_FILE="$(dirname "$0")/../config.json"
cat > ${CONFIG_FILE} << EOF
{
    "server": {
        "host": "${SERVER_IP}",
        "port": 5000
    },
    "nodes": {
        "Anshumaan": {
            "host": "${NODE1_IP}",
            "dme_port": 6001
        },
        "Sekhar": {
            "host": "${NODE2_IP}",
            "dme_port": 6002
        }
    }
}
EOF

echo ""
echo "Config file generated: ${CONFIG_FILE}"
cat ${CONFIG_FILE}
echo ""
echo "============================================="
echo " GCP Setup Complete!"
echo "============================================="
echo ""
echo "Next steps:"
echo "  1. Run: ./deploy.sh    (to copy code to all VMs)"
echo "  2. SSH into server VM:  gcloud compute ssh ${SERVER_VM} --zone=${ZONE}"
echo "  3. SSH into node1 VM:   gcloud compute ssh ${NODE1_VM} --zone=${ZONE}"
echo "  4. SSH into node2 VM:   gcloud compute ssh ${NODE2_VM} --zone=${ZONE}"
