#!/usr/bin/env bash
set -euo pipefail
SRC=/opt/data/james-bsc/cutover
# This is a restore recipe, not executed automatically.
# Copy into the Hermes-managed runtime location, then rewire absolute paths.
