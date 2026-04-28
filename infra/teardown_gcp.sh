#!/bin/bash
# =========================================================================
# teardown_gcp.sh - Delete all GCP resources for the chat room
# =========================================================================
# Run this AFTER you have finished testing and taken screenshots.
# This removes all VMs and firewall rules to stop billing.
# =========================================================================

set -e

ZONE="asia-south1-a"

echo "WARNING: This will delete all chatroom VMs and firewall rules."
read -p "Are you sure? (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

echo "Deleting VMs..."
gcloud compute instances delete chatroom-server --zone=${ZONE} --quiet 2>/dev/null || true
gcloud compute instances delete chatroom-node1 --zone=${ZONE} --quiet 2>/dev/null || true
gcloud compute instances delete chatroom-node2 --zone=${ZONE} --quiet 2>/dev/null || true

echo "Deleting firewall rule..."
gcloud compute firewall-rules delete allow-chatroom-ports --quiet 2>/dev/null || true

echo "Teardown complete."
