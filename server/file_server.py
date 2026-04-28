#!/usr/bin/env python3
"""
file_server.py - Shared File Server for Distributed Chat Room
==============================================================
Course: CCZG 526 - Distributed Computing
Group : 8

This module implements the file server node (Node 3) of the distributed
chat room system. It maintains the shared chat file (chat.txt) as the
central resource and exposes two operations via TCP sockets:

    VIEW  - Read the entire chat file and return contents
    POST  - Append a new message line to the chat file

The server uses a threading model to handle multiple concurrent VIEW
requests. POST requests are serialized at the application level through
the DME middleware on the client side, but the server also uses a local
file lock as an additional safety measure.

Protocol Format (over TCP):
    Request:  COMMAND|payload
    Response: STATUS|payload

Authors:
    Anshumaan Singh   (2025MT13006) - Server architecture & socket layer
    Chandra Sekhar G. (2025MT13026) - File I/O handling

Usage:
    python3 file_server.py [--config CONFIG_PATH]
"""

import os
import sys
import json
import socket
import threading
import argparse
import logging
from datetime import datetime


# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
CHAT_FILE = "chat.txt"              # name of the shared chat resource
BUFFER_SIZE = 4096                  # max bytes per recv call
FILE_LOCK = threading.Lock()        # local lock for file write safety
SERVER_LOG = "file_server.log"      # server-side activity log


def setup_logging(log_dir):
    """
    Configure logging to both console and a persistent log file.
    Log entries include timestamp, level, and the message so that
    we can trace every VIEW and POST event during evaluation.
    """
    log_path = os.path.join(log_dir, SERVER_LOG)
    logger = logging.getLogger("FileServer")
    logger.setLevel(logging.DEBUG)

    # console handler - shows INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    cfmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s",
                             datefmt="%d %b %Y %H:%M:%S")
    ch.setFormatter(cfmt)

    # file handler - captures everything including DEBUG
    fh = logging.FileHandler(log_path, mode='a')
    fh.setLevel(logging.DEBUG)
    ffmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s",
                             datefmt="%d %b %Y %H:%M:%S")
    fh.setFormatter(ffmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


def read_chat_file(filepath):
    """
    Read the entire contents of the shared chat file.
    Returns the file text or an empty string if the file does not
    exist yet (first run scenario).
    """
    if not os.path.exists(filepath):
        return ""
    with open(filepath, 'r') as f:
        contents = f.read()
    return contents


def append_to_chat_file(filepath, message_line):
    """
    Append a single formatted message line to the shared chat file.
    Uses the FILE_LOCK to guarantee atomic append even if two POST
    requests somehow arrive concurrently (belt-and-suspenders approach
    alongside the distributed mutual exclusion on the client side).
    """
    with FILE_LOCK:
        with open(filepath, 'a') as f:
            f.write(message_line + "\n")


def handle_client(conn, addr, chat_filepath, logger):
    """
    Handle a single client connection. The protocol is simple:
        - Receive a message of the form "COMMAND|payload"
        - Parse the command (VIEW or POST)
        - Execute the operation
        - Send back "OK|result" or "ERROR|reason"
    The connection is closed after one request-response cycle.
    """
    try:
        raw_data = conn.recv(BUFFER_SIZE).decode('utf-8').strip()
        if not raw_data:
            logger.warning("Empty request from %s", addr)
            conn.sendall(b"ERROR|Empty request")
            return

        logger.debug("Raw request from %s: %s", addr, raw_data)

        # split into command and payload
        parts = raw_data.split("|", 1)
        command = parts[0].upper()

        if command == "VIEW":
            # ---- VIEW operation ----
            logger.info("VIEW request from %s", addr)
            contents = read_chat_file(chat_filepath)
            if contents:
                response = "OK|" + contents
            else:
                response = "OK|"
            conn.sendall(response.encode('utf-8'))
            logger.info("VIEW response sent to %s (%d bytes)", addr,
                        len(contents))

        elif command == "POST":
            # ---- POST operation ----
            if len(parts) < 2 or not parts[1].strip():
                logger.warning("POST with empty payload from %s", addr)
                conn.sendall(b"ERROR|Empty message")
                return

            message_line = parts[1].strip()
            logger.info("POST request from %s: %s", addr, message_line)
            append_to_chat_file(chat_filepath, message_line)
            conn.sendall(b"OK|Message posted successfully")
            logger.info("POST completed for %s", addr)

        else:
            # unknown command
            logger.warning("Unknown command '%s' from %s", command, addr)
            conn.sendall(("ERROR|Unknown command: " + command).encode('utf-8'))

    except Exception as e:
        logger.error("Error handling client %s: %s", addr, str(e))
        try:
            conn.sendall(("ERROR|Server error: " + str(e)).encode('utf-8'))
        except Exception:
            pass
    finally:
        conn.close()


def start_server(host, port, chat_filepath, logger):
    """
    Start the TCP file server. Binds to the given host:port and
    spawns a new thread for each incoming connection so that
    multiple VIEW requests can be served concurrently.
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(5)

    logger.info("=" * 60)
    logger.info("File Server started on %s:%d", host, port)
    logger.info("Shared chat file: %s", os.path.abspath(chat_filepath))
    logger.info("=" * 60)

    # make sure the chat file exists
    if not os.path.exists(chat_filepath):
        open(chat_filepath, 'w').close()
        logger.info("Created empty chat file: %s", chat_filepath)

    try:
        while True:
            conn, addr = server_sock.accept()
            logger.debug("Accepted connection from %s", addr)
            # each client gets its own thread for concurrent reads
            t = threading.Thread(target=handle_client,
                                 args=(conn, addr, chat_filepath, logger))
            t.daemon = True
            t.start()
    except KeyboardInterrupt:
        logger.info("Server shutting down (keyboard interrupt)")
    finally:
        server_sock.close()
        logger.info("Server socket closed.")


def load_config(config_path):
    """
    Load server configuration from the JSON config file.
    Returns the server host and port.
    """
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config["server"]["host"], config["server"]["port"]


def main():
    """
    Entry point. Parse arguments, load config, and start the server.
    """
    parser = argparse.ArgumentParser(
        description="Distributed Chat Room - File Server (Node 3)")
    parser.add_argument("--config", type=str, default="../config.json",
                        help="Path to the configuration file")
    parser.add_argument("--host", type=str, default=None,
                        help="Override server bind address")
    parser.add_argument("--port", type=int, default=None,
                        help="Override server port")
    args = parser.parse_args()

    # set up logging
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger = setup_logging(log_dir)

    # determine host and port
    if args.host and args.port:
        host, port = args.host, args.port
    else:
        try:
            host, port = load_config(args.config)
        except (FileNotFoundError, KeyError) as e:
            logger.error("Config error: %s. Using defaults.", e)
            host, port = "0.0.0.0", 5000

    # allow binding to all interfaces on the server machine
    # regardless of what the config says (the config IP is for clients)
    bind_host = "0.0.0.0"

    # set up chat file path
    chat_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 CHAT_FILE)

    logger.info("Configuration loaded. Server will bind to %s:%d",
                bind_host, port)
    start_server(bind_host, port, chat_filepath, logger)


if __name__ == "__main__":
    main()
