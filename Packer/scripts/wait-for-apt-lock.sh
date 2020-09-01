#!/bin/bash
sleep 60
while fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do
    echo "dpkg lock - waiting on resources to free up"
    sleep 15
done
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 ; do
    echo "dpkg lock-frontend - waiting on resources to free up"
    sleep 15
done
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 ; do
    echo "apt lock  - waiting on resources to free up"
    sleep 15
done

sleep 15
while fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do
    echo "dpkg lock - waiting on resources to free up"
    sleep 15
done
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 ; do
    echo "dpkg lock-frontend - waiting on resources to free up"
    sleep 15
done
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 ; do
    echo "apt lock  - waiting on resources to free up"
    sleep 15
done
