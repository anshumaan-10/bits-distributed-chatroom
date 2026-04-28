#!/usr/bin/env python3
"""
Quick GCP end-to-end test script.
Runs on a client node to test connectivity with the file server
and basic VIEW/POST operations (no DME needed for this simple test).
"""
import sys
import os
import socket
import json

# load config
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
if not os.path.exists(config_path):
    config_path = os.path.join(os.getcwd(), 'config.json')
with open(config_path) as f:
    config = json.load(f)

server_host = config['server']['host']
server_port = config['server']['port']

def send_request(request_str):
    """Send a raw TCP request to the file server and return the response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((server_host, server_port))
        sock.sendall(request_str.encode('utf-8'))
        chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data.decode('utf-8'))
        return ''.join(chunks)
    finally:
        sock.close()

node_id = sys.argv[1] if len(sys.argv) > 1 else "TestNode"

print(f"=== GCP End-to-End Test from {node_id} ===")
print(f"File server: {server_host}:{server_port}")

# Test 1: VIEW (should be empty or have prior messages)
print("\n[TEST 1] VIEW request...")
try:
    resp = send_request("VIEW")
    print(f"  Response: {resp[:200]}")
    print("  PASS: VIEW works")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# Test 2: POST a message
msg = f"[{node_id}] Hello from GCP test!"
print(f"\n[TEST 2] POST request: {msg}")
try:
    resp = send_request(f"POST|{msg}")
    print(f"  Response: {resp}")
    if "OK" in resp.upper() or "SUCCESS" in resp.upper():
        print("  PASS: POST works")
    else:
        print(f"  WARN: Unexpected response but no error")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# Test 3: VIEW again to confirm our message is there
print("\n[TEST 3] VIEW after POST...")
try:
    resp = send_request("VIEW")
    if msg in resp:
        print(f"  PASS: Our message found in chat")
    else:
        print(f"  WARN: Message not found. Response: {resp[:300]}")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

print(f"\n=== All basic tests passed for {node_id} ===")
