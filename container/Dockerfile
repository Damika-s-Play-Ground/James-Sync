ARG HERMES_IMAGE=nousresearch/hermes-agent@sha256:1071a9e60d3d6c445a3f81d2534823e8954ad5a10b130a4ceba71e5722529432
FROM ${HERMES_IMAGE}

# The CLI is installed from an explicit npm version so a rebuild cannot
# silently pick up a different Codex binary. Bump this intentionally and
# review the resulting image before deploying it.
ARG CODEX_VERSION=0.155.1
RUN npm install --global --no-fund --no-audit "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

LABEL org.opencontainers.image.title="James Hermes runtime"
LABEL org.opencontainers.image.description="Pinned Hermes runtime plus James provider/runtime code"
LABEL org.opencontainers.image.source="https://github.com/Damika-s-Play-Ground/James-Sync"

ENV JAMES_REPO_ROOT=/opt/james \
    PYTHONPATH=/opt/james \
    PATH=/opt/james/bin:/opt/hermes/bin:/opt/hermes/.venv/bin:/opt/data/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Code is immutable in the image. Credentials, WhatsApp state, databases,
# logs, and media stay in /opt/data or the external secret mount.
COPY james /opt/james/james
COPY workspace /opt/james/workspace
COPY hermes /opt/james/hermes
COPY host-scripts /opt/james/host-scripts
COPY cron /opt/james/cron
COPY container/james-llm /opt/james/bin/james-llm
COPY container/entrypoint.sh /opt/james/entrypoint.sh
RUN chmod 0755 /opt/james/bin/james-llm /opt/james/entrypoint.sh \
    && python3 -m compileall -q /opt/james/james

ENTRYPOINT ["/opt/james/entrypoint.sh"]
