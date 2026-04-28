#!/bin/bash
# =========================================================================
# deploy.sh - Deploy code to all 3 GCP VMs
# =========================================================================
# Course: CCZG 526 - Distributed Computing
# Group : 8
#
# Option A — gcloud CLI (from Mac terminal with gcloud installed):
#   chmod +x deploy.sh && ./deploy.sh
#
# Option B — GCP Console browser SSH (recommended, no gcloud needed):
#   1. Open: https://console.cloud.google.com/compute/instances?project=avian-voice-433417-d5
#   2. dc-server1 → SSH → gear icon ⚙ → Upload file → infra/setup_server1_vm.py
#      Then in the SSH window: python3 setup_server1_vm.py
#   3. dc-client   → SSH → gear icon ⚙ → Upload file → infra/setup_client_vm.py
#      Then in the SSH window: python3 setup_client_vm.py
#   4. dc-server2  → SSH → gear icon ⚙ → Upload file → infra/setup_client_vm.py
#      Then in the SSH window: python3 setup_client_vm.py
# =========================================================================

set -e

ZONE="us-central1-a"
SERVER_VM="dc-server1"
NODE1_VM="dc-client"
NODE2_VM="dc-server2"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================="
echo " Deploying Distributed Chat Room"
echo " Source: ${PROJECT_DIR}"
echo "============================================="

# deploy to each VM
for VM in ${SERVER_VM} ${NODE1_VM} ${NODE2_VM}; do
    echo ""
    echo "---- Deploying to ${VM} ----"

    # create the project directory on the VM
    gcloud compute ssh ${VM} --zone=${ZONE} --command="mkdir -p ~/distributed-chatroom/{server,middleware,client,logs}"

    # copy the files
    gcloud compute scp --zone=${ZONE} --recurse \
        ${PROJECT_DIR}/server/ ${VM}:~/distributed-chatroom/server/
    gcloud compute scp --zone=${ZONE} --recurse \
        ${PROJECT_DIR}/middleware/ ${VM}:~/distributed-chatroom/middleware/
    gcloud compute scp --zone=${ZONE} --recurse \
        ${PROJECT_DIR}/client/ ${VM}:~/distributed-chatroom/client/
    gcloud compute scp --zone=${ZONE} \
        ${PROJECT_DIR}/config.json ${VM}:~/distributed-chatroom/config.json

    echo "  Done: ${VM}"
done

echo ""
echo "============================================="
echo " Deployment Complete!"
echo "============================================="
echo ""
echo "To start the system:"
echo ""
echo "  1. Start file server (on ${SERVER_VM}):"
echo "     gcloud compute ssh ${SERVER_VM} --zone=${ZONE} -- 'cd ~/distributed-chatroom && python3 server/file_server.py --config config.json'"
echo ""
echo "  2. Start user node 1 (on ${NODE1_VM}):"
echo "     gcloud compute ssh ${NODE1_VM} --zone=${ZONE}"
echo "     cd ~/distributed-chatroom && python3 client/chat_app.py --node-id Anshumaan --config config.json"
echo ""
echo "  3. Start user node 2 (on ${NODE2_VM}):"
echo "     gcloud compute ssh ${NODE2_VM} --zone=${ZONE}"
echo "     cd ~/distributed-chatroom && python3 client/chat_app.py --node-id Sekhar --config config.json"
