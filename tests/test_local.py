#!/usr/bin/env python3
"""
test_local.py - Local Integration Test for Distributed Chat Room
=================================================================
Course: CCZG 526 - Distributed Computing
Group : 8

This script runs all three components (file server + 2 user nodes) on
localhost with different ports to verify the system works correctly
before deploying to GCP.

Test Cases:
    TC1 - Single user posts a message and views it
    TC2 - Both users can view simultaneously
    TC3 - Both users post concurrently (DME prevents conflicts)
    TC4 - Rapid sequential posts from alternating users
    TC5 - View after multiple posts shows correct ordering

Authors:
    Anshumaan Singh    (2025MT13006) - Test design & orchestration
    Prasanna Kumar M.  (2025MT13063) - Test case specification

Usage:
    python3 test_local.py
"""

import os
import sys
import json
import time
import socket
import subprocess
import threading
import signal

# add parent directory to the module path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from client.server_client import send_view, send_post
from middleware.dme import DMENode


# ---------------------------------------------------------------------------
# Test configuration: all on localhost with unique ports
# ---------------------------------------------------------------------------
LOCAL_CONFIG = {
    "server": {"host": "127.0.0.1", "port": 15000},
    "nodes": {
        "TestUser1": {"host": "127.0.0.1", "dme_port": 16001},
        "TestUser2": {"host": "127.0.0.1", "dme_port": 16002}
    }
}

TEST_CONFIG_PATH = "/tmp/chatroom_test_config.json"
SERVER_PROC = None
PASS_COUNT = 0
FAIL_COUNT = 0


def write_test_config():
    """Write the local test configuration to a temp file."""
    with open(TEST_CONFIG_PATH, 'w') as f:
        json.dump(LOCAL_CONFIG, f)


def start_file_server():
    """Start the file server as a subprocess."""
    global SERVER_PROC
    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "server", "file_server.py")
    # remove old chat file if it exists
    chat_file = os.path.join(os.path.dirname(server_script), "chat.txt")
    if os.path.exists(chat_file):
        os.remove(chat_file)

    SERVER_PROC = subprocess.Popen(
        [sys.executable, server_script,
         "--host", "127.0.0.1", "--port", "15000"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    # give the server a moment to bind
    time.sleep(1)
    print("[Setup] File server started (PID: {})".format(SERVER_PROC.pid))


def stop_file_server():
    """Stop the file server subprocess."""
    global SERVER_PROC
    if SERVER_PROC:
        SERVER_PROC.terminate()
        SERVER_PROC.wait()
        print("[Teardown] File server stopped.")


def report(test_name, passed, detail=""):
    """Print test result and update counters."""
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    msg = "  [{}] {}".format(status, test_name)
    if detail:
        msg += " - {}".format(detail)
    print(msg)


def wait_for_server(host, port, timeout=5):
    """Wait until the server is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            time.sleep(0.2)
    return False


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_tc1_single_post_and_view():
    """TC1: Single user posts a message and then views it."""
    print("\n--- TC1: Single Post and View ---")
    host = LOCAL_CONFIG["server"]["host"]
    port = LOCAL_CONFIG["server"]["port"]

    # post a message
    msg = "25 Apr 9:01AM TestUser1: Hello World"
    success, resp = send_post(host, port, msg)
    report("TC1a - Post message", success, resp)

    # view and check
    contents = send_view(host, port)
    found = "Hello World" in contents
    report("TC1b - View contains posted message", found,
           "Got: {}".format(contents.strip()[:80]))


def test_tc2_concurrent_views():
    """TC2: Both users view simultaneously (no locking needed for reads)."""
    print("\n--- TC2: Concurrent Views ---")
    host = LOCAL_CONFIG["server"]["host"]
    port = LOCAL_CONFIG["server"]["port"]

    results = [None, None]
    errors = [None, None]

    def do_view(idx):
        try:
            results[idx] = send_view(host, port)
        except Exception as e:
            errors[idx] = str(e)

    t1 = threading.Thread(target=do_view, args=(0,))
    t2 = threading.Thread(target=do_view, args=(1,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    both_ok = (results[0] is not None and results[1] is not None
               and errors[0] is None and errors[1] is None)
    report("TC2 - Both users view concurrently", both_ok,
           "User1 err={}, User2 err={}".format(errors[0], errors[1]))

    if both_ok:
        same = results[0].strip() == results[1].strip()
        report("TC2b - Both see same content", same)


def test_tc3_concurrent_posts_with_dme():
    """TC3: Both users post at the same time, DME ensures mutual exclusion."""
    print("\n--- TC3: Concurrent Posts with DME ---")
    host = LOCAL_CONFIG["server"]["host"]
    port = LOCAL_CONFIG["server"]["port"]

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "logs")

    # build peer dicts for each user
    peers1 = {"TestUser2": ("127.0.0.1", 16002)}
    peers2 = {"TestUser1": ("127.0.0.1", 16001)}

    # initialize DME nodes
    dme1 = DMENode("TestUser1", 16001, peers1, log_dir)
    dme2 = DMENode("TestUser2", 16002, peers2, log_dir)

    # give DME listeners a moment to start
    time.sleep(0.5)

    results = {"user1": None, "user2": None}

    def post_with_dme(dme_node, user_id, message, key):
        """Post a message using the DME protocol."""
        try:
            dme_node.request_cs()
            formatted = "25 Apr 9:10AM {}: {}".format(user_id, message)
            success, resp = send_post(host, port, formatted)
            results[key] = success
            time.sleep(0.3)  # simulate some work in critical section
            dme_node.release_cs()
        except Exception as e:
            print("  Error in {}: {}".format(user_id, e))
            results[key] = False
            try:
                dme_node.release_cs()
            except Exception:
                pass

    t1 = threading.Thread(target=post_with_dme,
                          args=(dme1, "TestUser1", "Message from User1", "user1"))
    t2 = threading.Thread(target=post_with_dme,
                          args=(dme2, "TestUser2", "Message from User2", "user2"))

    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    both_posted = (results["user1"] is True and results["user2"] is True)
    report("TC3 - Both users posted with DME", both_posted,
           "User1={}, User2={}".format(results["user1"], results["user2"]))

    # verify both messages appear in the file
    contents = send_view(host, port)
    has_u1 = "Message from User1" in contents
    has_u2 = "Message from User2" in contents
    report("TC3b - Both messages in chat file", has_u1 and has_u2)

    # check DME logs exist
    log1 = os.path.join(log_dir, "dme_node_TestUser1.log")
    log2 = os.path.join(log_dir, "dme_node_TestUser2.log")
    logs_exist = os.path.exists(log1) and os.path.exists(log2)
    report("TC3c - DME log files created", logs_exist)

    if logs_exist:
        with open(log1, 'r') as f:
            log1_content = f.read()
        has_request = "REQUEST" in log1_content
        has_reply = "REPLY" in log1_content
        has_release = "RELEASE" in log1_content
        report("TC3d - DME logs contain REQUEST/REPLY/RELEASE",
               has_request and has_reply and has_release)


def test_tc4_sequential_posts():
    """TC4: Alternating posts from both users."""
    print("\n--- TC4: Sequential Alternating Posts ---")
    host = LOCAL_CONFIG["server"]["host"]
    port = LOCAL_CONFIG["server"]["port"]

    messages = [
        "25 Apr 9:20AM TestUser1: First message",
        "25 Apr 9:21AM TestUser2: Second message",
        "25 Apr 9:22AM TestUser1: Third message",
    ]
    all_ok = True
    for msg in messages:
        success, _ = send_post(host, port, msg)
        if not success:
            all_ok = False

    report("TC4 - Sequential posts all succeeded", all_ok)

    contents = send_view(host, port)
    has_all = all(m.split(": ", 1)[1] in contents for m in messages)
    report("TC4b - All messages present in chat file", has_all)


def test_tc5_view_shows_all():
    """TC5: View after all tests shows complete message history."""
    print("\n--- TC5: Final View Shows All Messages ---")
    host = LOCAL_CONFIG["server"]["host"]
    port = LOCAL_CONFIG["server"]["port"]

    contents = send_view(host, port)
    lines = [l for l in contents.strip().split("\n") if l.strip()]
    # we posted at least: TC1(1) + TC3(2) + TC4(3) = 6 messages
    has_enough = len(lines) >= 6
    report("TC5 - Chat file has all messages ({} lines)".format(len(lines)),
           has_enough)
    print("\n  Final chat file contents:")
    for line in lines:
        print("    " + line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("  Distributed Chat Room - Local Integration Tests")
    print("  Group 8 - CCZG 526")
    print("=" * 60)

    write_test_config()
    start_file_server()

    if not wait_for_server("127.0.0.1", 15000):
        print("[Error] File server did not start. Aborting tests.")
        stop_file_server()
        sys.exit(1)

    try:
        test_tc1_single_post_and_view()
        test_tc2_concurrent_views()
        test_tc3_concurrent_posts_with_dme()
        test_tc4_sequential_posts()
        test_tc5_view_shows_all()
    except Exception as e:
        print("\n[Error] Test execution failed: {}".format(e))
        import traceback
        traceback.print_exc()
    finally:
        stop_file_server()

    print("\n" + "=" * 60)
    print("  Results: {} PASSED, {} FAILED".format(PASS_COUNT, FAIL_COUNT))
    print("=" * 60)

    if FAIL_COUNT > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
