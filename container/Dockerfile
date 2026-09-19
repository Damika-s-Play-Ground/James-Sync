ARG HERMES_IMAGE=nousresearch/hermes-agent@sha256:1071a9e60d3d6c445a3f81d2534823e8954ad5a10b130a4ceba71e5722529432
FROM ${HERMES_IMAGE}

# The CLI is installed from an explicit npm version so a rebuild cannot
# silently pick up a different Codex binary. Bump this intentionally and
# review the resulting image before deploying it.
ARG CODEX_VERSION=0.155.1
RUN npm install --global --no-fund --no-audit "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

ARG WACLI_VERSION=0.18.2
ARG WACLI_SHA256=d33e8cc4b01acbd4e1ba212e22ac9c6438221e0761112dd3e7a2cc30b3a5946f
RUN curl --fail --location --silent --show-error \
      "https://github.com/openclaw/wacli/releases/download/v${WACLI_VERSION}/wacli_${WACLI_VERSION}_linux_amd64.tar.gz" \
      --output /tmp/wacli.tar.gz \
    && echo "${WACLI_SHA256}  /tmp/wacli.tar.gz" | sha256sum -c - \
    && mkdir -p /tmp/wacli \
    && tar -xzf /tmp/wacli.tar.gz -C /tmp/wacli \
    && install -m 0755 /tmp/wacli/wacli /usr/local/bin/wacli \
    && rm -rf /tmp/wacli /tmp/wacli.tar.gz

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
COPY container/runtime-init.sh /opt/james/container/runtime-init.sh
RUN chmod 0755 /opt/james/bin/james-llm /opt/james/entrypoint.sh /opt/james/container/runtime-init.sh \
    && python3 -m compileall -q /opt/james/james

ENTRYPOINT ["/opt/james/entrypoint.sh"]
