#!/bin/sh
touch session.dat
aria2c --enable-rpc --rpc-listen-all --rpc-allow-origin-all=true --no-conf=true --input=session.dat --save-session=session.dat --save-session-interval=60 --auto-file-renaming=false
