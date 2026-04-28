#!/usr/bin/env python3
"""
server_client.py - Network Client for File Server Communication
================================================================
Course: CCZG 526 - Distributed Computing
Group : 8

This module provides a simple TCP client that communicates with the
file server node. It implements two operations:

    send_view()  - Fetch the current chat file contents from the server
    send_post()  - Send a formatted message to be appended to the chat file

The communication protocol matches the file server's expectation:
    Request:  "COMMAND|payload"
    Response: "STATUS|payload"

Authors:
    Anshumaan Singh    (2025MT13006) - Protocol design & error handling
    Prasanna Kumar M.  (2025MT13063) - Network testing & validation
"""

import socket


# maximum bytes we expect in a response from the file server
RECV_BUFFER = 8192


def send_view(server_host, server_port):
    """
    Send a VIEW request to the file server and return the chat contents.

    Parameters:
        server_host : IP address of the file server node
        server_port : TCP port the file server is listening on

    Returns:
        String containing the chat file contents, or an error message.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((server_host, server_port))
        sock.sendall(b"VIEW|")

        # receive response - may need multiple recv calls for large files
        chunks = []
        while True:
            chunk = sock.recv(RECV_BUFFER)
            if not chunk:
                break
            chunks.append(chunk)
        sock.close()

        response = b"".join(chunks).decode('utf-8')

        # parse response: "OK|content" or "ERROR|reason"
        if response.startswith("OK|"):
            return response[3:]     # strip the "OK|" prefix
        else:
            return "[Error] " + response

    except socket.timeout:
        return "[Error] Server not responding (connection timed out)"
    except ConnectionRefusedError:
        return "[Error] Cannot connect to file server - is it running?"
    except Exception as e:
        return "[Error] " + str(e)


def send_post(server_host, server_port, formatted_message):
    """
    Send a POST request to the file server with the formatted message.

    The message should already be formatted with timestamp and user ID
    by the calling application (e.g., "25 Apr 10:30AM Anshumaan: Hello").

    Parameters:
        server_host      : IP address of the file server node
        server_port      : TCP port the file server is listening on
        formatted_message: complete message line to append to chat file

    Returns:
        True if the post was successful, False otherwise.
        Also returns the server response message as second element.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((server_host, server_port))

        # construct POST request
        request = "POST|" + formatted_message
        sock.sendall(request.encode('utf-8'))

        # wait for server acknowledgment
        response = sock.recv(RECV_BUFFER).decode('utf-8')
        sock.close()

        if response.startswith("OK|"):
            return True, response[3:]
        else:
            return False, response

    except socket.timeout:
        return False, "Server not responding (connection timed out)"
    except ConnectionRefusedError:
        return False, "Cannot connect to file server - is it running?"
    except Exception as e:
        return False, str(e)
