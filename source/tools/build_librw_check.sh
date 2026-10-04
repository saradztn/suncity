#!/bin/sh
# Created by: Arena.ai Agent Mode (AI) - MTA:SA asset pipelines (shared tool, also used by FishingRod / Castle)
# Builds the reference-loader check against aap/librw (NULL platform). Needs: git, cmake, g++.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -d /tmp/librw ] || git clone --depth 1 https://github.com/aap/librw.git /tmp/librw
mkdir -p /tmp/librw/build && cd /tmp/librw/build
cmake .. -DLIBRW_PLATFORM=NULL -DLIBRW_TOOLS=OFF -DLIBRW_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
make -j2 >/dev/null 2>&1
g++ -std=c++14 -O1 -w -I/tmp/librw -I/tmp/librw/src "$HERE/librw_check.cpp" /tmp/librw/build/src/librw.a -o /tmp/librw_check
echo built /tmp/librw_check
