#!/usr/bin/env python3
"""
chat_app.py - Distributed Chat Room CLI Application
=====================================================
Course: CCZG 526 - Distributed Computing
Group : 8

This is the main user-facing application that runs on each user node
(Node 1 and Node 2). It provides a command-line interface with two
operations:

    view              - Display all messages from the shared chat file
    post <message>    - Post a new message (requires DME lock)

The application integrates with:
    - The DME middleware (middleware/dme.py) for mutual exclusion on posts
    - The server client (client/server_client.py) for file server access

Architecture:
    User CLI  --->  chat_app.py  --->  DME middleware (for post locking)
                                 --->  server_client   (for file server I/O)

Authors:
    Hari Teja M.G.    (2025MT13014) - CLI interface & command parsing
    Anshumaan Singh   (2025MT13006) - Application-middleware integration

Usage:
    python3 chat_app.py --node-id Anshumaan --config ../config.json
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime

# add parent directory to path so we can import the middleware module
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from middleware.dme import DMENode
from client.server_client import send_view, send_post


def load_config(config_path):
    """
    Load the configuration file and return the parsed JSON object.
    The config contains server address/port and all node details
    needed to set up DME peer connections.
    """
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config


def format_message(node_id, text):
    """
    Format a chat message with the current timestamp from the user's
    machine (not the server time, as per the assignment requirement).

    Format: "DD Mon HH:MMAM/PM NodeId: message text"
    Example: "25 Apr 10:30AM Anshumaan: Hello everyone"
    """
    now = datetime.now()
    # format: "25 Apr 9:04AM" - matching the sample format in the assignment
    timestamp = now.strftime("%-d %b %-I:%M%p")
    return "{} {}: {}".format(timestamp, node_id, text)


def print_banner(node_id):
    """Display a welcome banner when the application starts."""
    print("=" * 60)
    print("  Distributed Chat Room - CCZG 526 Assignment")
    print("  Group 8")
    print("  Node: {}".format(node_id))
    print("=" * 60)
    print()
    print("Commands:")
    print("  view                - View all messages")
    print("  post <message>      - Post a new message")
    print("  post \"<message>\"    - Post message (with quotes)")
    print("  status              - Show DME queue state")
    print("  exit / quit         - Exit the application")
    print()


def parse_post_command(user_input):
    """
    Extract the message text from a post command.
    Handles both:
        post Hello everyone
        post "Hello everyone"
    Returns the message text or None if parsing fails.
    """
    # strip the 'post' prefix
    text = user_input[4:].strip()

    if not text:
        return None

    # remove surrounding quotes if present
    if (text.startswith('"') and text.endswith('"')) or \
       (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()

    return text if text else None


def run_view(server_host, server_port):
    """
    Execute the VIEW command: fetch and display chat contents.
    No DME lock is needed for reading (multiple concurrent reads allowed).
    """
    contents = send_view(server_host, server_port)
    if contents:
        print(contents)
    else:
        print("(No messages yet)")


def run_post(node_id, text, server_host, server_port, dme_node):
    """
    Execute the POST command with DME protection.
    Sequence:
        1. Request critical section (blocks until granted)
        2. Format the message with local timestamp
        3. Send POST to file server
        4. Release critical section
    """
    print("[DME] Requesting write access...")

    # step 1: acquire distributed lock
    dme_node.request_cs()
    print("[DME] Write access granted.")

    try:
        # step 2: format message with local timestamp
        formatted_msg = format_message(node_id, text)

        # step 3: send to file server
        success, response = send_post(server_host, server_port, formatted_msg)
        if success:
            print("Message posted: {}".format(formatted_msg))
        else:
            print("[Error] Failed to post: {}".format(response))
    finally:
        # step 4: always release the lock, even if posting failed
        dme_node.release_cs()
        print("[DME] Write access released.")


def main():
    """
    Main entry point. Sets up configuration, initializes the DME node,
    and runs the interactive command loop.
    """
    parser = argparse.ArgumentParser(
        description="Distributed Chat Room - User Node")
    parser.add_argument("--node-id", type=str, required=True,
                        help="Unique ID for this node (e.g., Anshumaan)")
    parser.add_argument("--config", type=str, default="../config.json",
                        help="Path to the configuration file")
    args = parser.parse_args()

    node_id = args.node_id

    # load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print("[Error] Config file not found: {}".format(args.config))
        sys.exit(1)
    except json.JSONDecodeError:
        print("[Error] Invalid JSON in config file: {}".format(args.config))
        sys.exit(1)

    # extract server connection details
    server_host = config["server"]["host"]
    server_port = config["server"]["port"]

    # verify that this node_id exists in the config
    if node_id not in config["nodes"]:
        print("[Error] Node '{}' not found in config. Available nodes: {}".format(
            node_id, list(config["nodes"].keys())))
        sys.exit(1)

    # determine this node's DME port
    my_dme_port = config["nodes"][node_id]["dme_port"]

    # build the peer list (all nodes except ourselves)
    peers = {}
    for nid, ninfo in config["nodes"].items():
        if nid != node_id:
            peers[nid] = (ninfo["host"], ninfo["dme_port"])

    # set up log directory
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "logs")

    # initialize the DME middleware node
    print("Initializing DME middleware...")
    dme_node = DMENode(node_id, my_dme_port, peers, log_dir)
    print("DME middleware ready. Peers: {}".format(list(peers.keys())))

    # display the welcome banner
    print_banner(node_id)

    # main command loop
    prompt = "{}_machine> ".format(node_id)
    while True:
        try:
            user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # parse the command
        cmd = user_input.lower().split()[0]

        if cmd == "view":
            run_view(server_host, server_port)

        elif cmd == "post":
            text = parse_post_command(user_input)
            if text is None:
                print("Usage: post <message>")
                print("       post \"your message here\"")
            else:
                run_post(node_id, text, server_host, server_port, dme_node)

        elif cmd == "status":
            # debug command to inspect DME state
            queue = dme_node.get_queue_state()
            clock = dme_node.get_clock()
            print("Lamport Clock: {}".format(clock))
            print("Request Queue: {}".format(queue))

        elif cmd in ("exit", "quit"):
            print("Goodbye!")
            break

        else:
            print("Unknown command: '{}'. Use 'view', 'post', or 'exit'.".format(cmd))


if __name__ == "__main__":
    main()
