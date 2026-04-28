#!/usr/bin/env python3
"""
dme.py - Distributed Mutual Exclusion using Lamport's Algorithm
================================================================
Course: CCZG 526 - Distributed Computing
Group : 8

This module implements Lamport's Distributed Mutual Exclusion algorithm
as described in:
    Lamport, L. (1978). "Time, clocks, and the ordering of events in
    a distributed system." Communications of the ACM, 21(7), 558-565.

The algorithm ensures that at most one node can enter the critical section
(write access to the shared chat file) at any point in time, without
relying on a centralized coordinator.

Algorithm Summary:
    1. When a node wants to enter the critical section, it increments its
       logical clock, timestamps a REQUEST message, adds it to its own
       request queue, and broadcasts the REQUEST to all other peer nodes.
    2. On receiving a REQUEST, a node adds it to its queue, updates its
       logical clock, and sends a REPLY.
    3. A node may enter the critical section when:
       (a) Its own request is at the front of the queue (sorted by
           timestamp; ties broken by node ID), AND
       (b) It has received a message from every other node with a
           timestamp greater than its own request's timestamp.
    4. After leaving the critical section, the node removes its request
       from the queue and broadcasts a RELEASE to all peers.
    5. On receiving a RELEASE, a node removes the sender's request from
       its own queue.

Message Types (exchanged between peer nodes via TCP):
    REQUEST|timestamp|sender_id
    REPLY|timestamp|sender_id
    RELEASE|timestamp|sender_id

Authors:
    Anshumaan Singh   (2025MT13006) - Core DME algorithm design & implementation
    Hari Teja M.G.    (2025MT13014) - Message serialization & queue management

Usage:
    This module is imported by the chat application (chat_app.py).
    It is NOT run standalone.
"""

import socket
import threading
import json
import os
import logging
from datetime import datetime


# ---------------------------------------------------------------------------
# DME Message Types
# ---------------------------------------------------------------------------
MSG_REQUEST = "REQUEST"
MSG_REPLY = "REPLY"
MSG_RELEASE = "RELEASE"

# buffer size for TCP communication between DME peers
DME_BUFFER_SIZE = 2048


class LamportClock:
    """
    Logical clock following Lamport's "happens-before" relation.
    The clock is a simple counter that increments on local events
    and adjusts on receiving messages with higher timestamps.
    Thread-safe implementation using a lock.
    """

    def __init__(self):
        self._time = 0
        self._lock = threading.Lock()

    def tick(self):
        """Increment clock for a local event and return new value."""
        with self._lock:
            self._time += 1
            return self._time

    def update(self, received_time):
        """
        Update clock based on received message timestamp.
        Sets local clock to max(local, received) + 1 as per
        Lamport's rule for message receipt.
        """
        with self._lock:
            self._time = max(self._time, received_time) + 1
            return self._time

    @property
    def current(self):
        """Return current clock value without modification."""
        with self._lock:
            return self._time


class DMENode:
    """
    Distributed Mutual Exclusion node implementing Lamport's algorithm.

    Each user node in the chat system creates one instance of this class.
    The node runs a background listener thread that handles incoming
    REQUEST, REPLY, and RELEASE messages from peer nodes.

    The request_cs() and release_cs() methods are called by the chat
    application before and after posting a message.
    """

    def __init__(self, node_id, my_dme_port, peers, log_dir):
        """
        Initialize the DME node.

        Parameters:
            node_id    : string identifier for this node (e.g., "Anshumaan")
            my_dme_port: TCP port this node listens on for DME messages
            peers      : dict of {peer_id: (host, port)} for other user nodes
            log_dir    : directory path for writing DME log files
        """
        self.node_id = node_id
        self.my_dme_port = my_dme_port
        self.peers = peers              # {peer_id: (host, port)}
        self.clock = LamportClock()     # Lamport logical clock

        # request queue: list of (timestamp, node_id) tuples
        # sorted by timestamp first, then node_id for tie-breaking
        self.request_queue = []
        self.queue_lock = threading.Lock()

        # track replies received for the current request round
        self.replies_received = set()
        self.reply_lock = threading.Lock()

        # event to signal when we can enter the critical section
        self.cs_granted = threading.Event()

        # flag indicating whether this node is currently requesting CS
        self.requesting = False
        self.my_request_ts = None

        # set up dedicated DME logger
        self.logger = self._setup_logger(log_dir)

        # start the listener thread for incoming DME messages
        self.listener_thread = threading.Thread(target=self._listen,
                                                daemon=True)
        self.listener_thread.start()
        self._log("info", "DME node '%s' initialized, listening on port %d",
                  self.node_id, self.my_dme_port)

    def _setup_logger(self, log_dir):
        """
        Create a logger that writes DME events to a separate log file.
        This log is crucial for demonstrating that the DME algorithm
        is actually controlling access to the shared resource.
        """
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "dme_node_{}.log".format(self.node_id))

        logger = logging.getLogger("DME_" + self.node_id)
        logger.setLevel(logging.DEBUG)

        # avoid adding duplicate handlers on re-initialization
        if logger.handlers:
            logger.handlers.clear()

        # file handler for persistent log
        fh = logging.FileHandler(log_file, mode='a')
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "[%(asctime)s] [Clock=%(clock)s] %(levelname)s: %(message)s",
            datefmt="%d %b %Y %H:%M:%S"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        # console handler for real-time visibility
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        return logger

    def _log(self, level, msg, *args):
        """Helper to attach current Lamport clock value to log entries."""
        extra = {"clock": self.clock.current}
        if level == "info":
            self.logger.info(msg, *args, extra=extra)
        elif level == "debug":
            self.logger.debug(msg, *args, extra=extra)
        elif level == "warning":
            self.logger.warning(msg, *args, extra=extra)

    # -------------------------------------------------------------------
    # Network: sending messages to peers
    # -------------------------------------------------------------------

    def _send_message(self, peer_id, msg_type, timestamp):
        """
        Send a DME protocol message to a specific peer node.
        Message format: "TYPE|timestamp|sender_id"
        Uses a fresh TCP connection for each message (simple and reliable).
        """
        peer_host, peer_port = self.peers[peer_id]
        message = "{}|{}|{}".format(msg_type, timestamp, self.node_id)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((peer_host, peer_port))
            sock.sendall(message.encode('utf-8'))
            sock.close()
            self._log("debug", "SENT %s(ts=%d) to %s",
                      msg_type, timestamp, peer_id)
        except Exception as e:
            self._log("warning", "Failed to send %s to %s: %s",
                      msg_type, peer_id, str(e))

    def _broadcast(self, msg_type, timestamp):
        """Broadcast a DME message to all peer nodes."""
        for peer_id in self.peers:
            self._send_message(peer_id, msg_type, timestamp)

    # -------------------------------------------------------------------
    # Network: listening for incoming DME messages
    # -------------------------------------------------------------------

    def _listen(self):
        """
        Background thread that listens for incoming DME messages.
        Each incoming connection carries exactly one message.
        """
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind(("0.0.0.0", self.my_dme_port))
        listen_sock.listen(10)

        while True:
            try:
                conn, addr = listen_sock.accept()
                data = conn.recv(DME_BUFFER_SIZE).decode('utf-8').strip()
                conn.close()
                if data:
                    # process message in a separate thread to avoid blocking
                    t = threading.Thread(target=self._handle_message,
                                         args=(data,), daemon=True)
                    t.start()
            except Exception as e:
                self._log("warning", "Listener error: %s", str(e))

    def _handle_message(self, raw_message):
        """
        Parse and process an incoming DME message.
        The three message types trigger different actions as per
        Lamport's algorithm.
        """
        parts = raw_message.split("|")
        if len(parts) != 3:
            self._log("warning", "Malformed message: %s", raw_message)
            return

        msg_type = parts[0]
        msg_timestamp = int(parts[1])
        sender_id = parts[2]

        # update our logical clock based on received timestamp
        self.clock.update(msg_timestamp)

        if msg_type == MSG_REQUEST:
            self._handle_request(msg_timestamp, sender_id)
        elif msg_type == MSG_REPLY:
            self._handle_reply(msg_timestamp, sender_id)
        elif msg_type == MSG_RELEASE:
            self._handle_release(msg_timestamp, sender_id)
        else:
            self._log("warning", "Unknown DME message type: %s", msg_type)

    def _handle_request(self, timestamp, sender_id):
        """
        Handle an incoming REQUEST message.
        Per Lamport's algorithm:
            - Add the request to our local queue
            - Send a REPLY to the requester
            - Check if conditions for entering CS are now met
        """
        self._log("info", "RECV REQUEST(ts=%d) from %s", timestamp, sender_id)

        # add sender's request to our priority queue
        with self.queue_lock:
            self.request_queue.append((timestamp, sender_id))
            # keep queue sorted: by timestamp first, then by node_id
            self.request_queue.sort(key=lambda x: (x[0], x[1]))

        # always reply to a REQUEST (Lamport's rule)
        reply_ts = self.clock.tick()
        self._send_message(sender_id, MSG_REPLY, reply_ts)
        self._log("info", "SENT REPLY(ts=%d) to %s", reply_ts, sender_id)

        # check if we can now enter CS (our queue position may have changed)
        self._check_cs_entry()

    def _handle_reply(self, timestamp, sender_id):
        """
        Handle an incoming REPLY message.
        Track that we have received a reply from this peer.
        If replies from all peers are in, check CS entry condition.
        """
        self._log("info", "RECV REPLY(ts=%d) from %s", timestamp, sender_id)

        with self.reply_lock:
            self.replies_received.add(sender_id)

        # check if all replies are in and we are at head of queue
        self._check_cs_entry()

    def _handle_release(self, timestamp, sender_id):
        """
        Handle an incoming RELEASE message.
        Remove the sender's request from our local queue and
        re-check if we can now enter the CS.
        """
        self._log("info", "RECV RELEASE(ts=%d) from %s", timestamp, sender_id)

        with self.queue_lock:
            # remove the sender's oldest request from the queue
            self.request_queue = [
                (ts, nid) for (ts, nid) in self.request_queue
                if nid != sender_id
            ]

        # with the sender's request removed, we might now be at the head
        self._check_cs_entry()

    # -------------------------------------------------------------------
    # Critical Section management
    # -------------------------------------------------------------------

    def _check_cs_entry(self):
        """
        Check if both conditions for entering the critical section are met:
            1. Our request is at the head of the priority queue
            2. We have received REPLY from every peer node

        If both conditions hold, signal the cs_granted event so that
        the requesting thread (in request_cs) can proceed.
        """
        if not self.requesting:
            return

        with self.queue_lock:
            if not self.request_queue:
                return
            head_ts, head_id = self.request_queue[0]

        # condition 1: our request must be at the front
        if head_id != self.node_id:
            return

        # condition 2: must have received reply from every peer
        with self.reply_lock:
            all_replied = (len(self.replies_received) == len(self.peers))

        if all_replied:
            self._log("info",
                      "CS CONDITIONS MET: head of queue (ts=%d) "
                      "and all %d replies received",
                      head_ts, len(self.peers))
            self.cs_granted.set()

    def request_cs(self):
        """
        Request entry into the critical section.
        This is a BLOCKING call that returns only when this node has
        been granted exclusive access.

        Called by the chat application before executing a POST command.

        Steps:
            1. Increment logical clock
            2. Create a REQUEST with current timestamp
            3. Add own request to the priority queue
            4. Broadcast REQUEST to all peers
            5. Wait until cs_granted event is signalled
        """
        self._log("info", "===== REQUESTING CRITICAL SECTION =====")

        # reset state for this request round
        self.cs_granted.clear()
        with self.reply_lock:
            self.replies_received = set()

        # get timestamp for our request
        request_ts = self.clock.tick()
        self.my_request_ts = request_ts
        self.requesting = True

        # add our own request to the queue
        with self.queue_lock:
            self.request_queue.append((request_ts, self.node_id))
            self.request_queue.sort(key=lambda x: (x[0], x[1]))

        self._log("info", "Broadcast REQUEST(ts=%d) to all peers", request_ts)

        # broadcast REQUEST to all peer nodes
        self._broadcast(MSG_REQUEST, request_ts)

        # block until we are granted access
        self._log("info", "Waiting for CS grant...")
        self.cs_granted.wait()
        self._log("info", "===== ENTERED CRITICAL SECTION =====")

    def release_cs(self):
        """
        Release the critical section after completing the POST operation.
        Called by the chat application after the POST is done.

        Steps:
            1. Remove own request from the queue
            2. Broadcast RELEASE to all peers
            3. Clear the requesting flag
        """
        self._log("info", "===== RELEASING CRITICAL SECTION =====")

        # remove our request from the queue
        with self.queue_lock:
            self.request_queue = [
                (ts, nid) for (ts, nid) in self.request_queue
                if nid != self.node_id
            ]

        # broadcast RELEASE so peers can update their queues
        release_ts = self.clock.tick()
        self._broadcast(MSG_RELEASE, release_ts)
        self._log("info", "Broadcast RELEASE(ts=%d) to all peers", release_ts)

        # reset flags
        self.requesting = False
        self.my_request_ts = None
        self._log("info", "===== CRITICAL SECTION RELEASED =====")

    def get_queue_state(self):
        """
        Return a snapshot of the current request queue.
        Useful for debugging and for the test harness.
        """
        with self.queue_lock:
            return list(self.request_queue)

    def get_clock(self):
        """Return current Lamport clock value."""
        return self.clock.current
