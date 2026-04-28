#!/bin/bash
# Fix the nested directory structure from SCP
cd ~/distributed-chatroom

# Fix server/
if [ -d "server/server" ]; then
    cp server/server/* server/ 2>/dev/null
    rm -rf server/server
    echo "Fixed server/"
fi

# Fix middleware/
if [ -d "middleware/middleware" ]; then
    cp middleware/middleware/* middleware/ 2>/dev/null
    rm -rf middleware/middleware
    echo "Fixed middleware/"
fi

# Fix client/
if [ -d "client/client" ]; then
    cp client/client/* client/ 2>/dev/null
    rm -rf client/client
    echo "Fixed client/"
fi

echo "Directory structure:"
find ~/distributed-chatroom -type f
