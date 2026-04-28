#!/bin/bash
# =========================================================================
# start_server.sh - Start the file server on dc-server1
# Run this FROM YOUR LOCAL MACHINE (not on the VM)
# =========================================================================
# Usage: bash infra/start_server.sh
# =========================================================================

ZONE="us-central1-a"
SERVER_VM="dc-server1"

echo "Starting file server on ${SERVER_VM}..."
gcloud compute ssh ${SERVER_VM} --zone=${ZONE} -- \
    "cd ~/distributed-chatroom && python3 server/file_server.py --config config.json"
