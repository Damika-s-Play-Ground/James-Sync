# Thin, reproducible James image.
#
# Hermes is kept in the upstream image.  James code and integrations will be
# added in a later layer once the Donely export has finished syncing; keeping
# this layer thin lets us update Hermes without rebuilding the whole system.
ARG HERMES_IMAGE=nousresearch/hermes-agent@sha256:1071a9e60d3d6c445a3f81d2534823e8954ad5a10b130a4ceba71e5722529432
FROM ${HERMES_IMAGE}

LABEL org.opencontainers.image.title="James Hermes runtime"
LABEL org.opencontainers.image.description="Pinned Hermes runtime for the James system"

# The upstream image owns the entrypoint and /opt/data contract.  Do not put
# credentials, WhatsApp state, databases, or media in this image.
