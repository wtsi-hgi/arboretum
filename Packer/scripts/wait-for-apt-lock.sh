#!/bin/bash
sleep 15
while fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do
    echo "Still running"
    sleep 15
done
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 ; do
    echo "Still running"
    sleep 15
done
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 ; do
    echo "Still running"
    sleep 15
done

apt update
sleep 15
while fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do
    echo "Still running"
    sleep 15
done
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 ; do
    echo "Still running"
    sleep 15
done
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 ; do
    echo "Still running"
    sleep 15
done
