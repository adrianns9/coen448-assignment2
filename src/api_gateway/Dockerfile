FROM kong:latest

USER root

# Install envsubst and dos2unix
RUN apt-get update && \
    apt-get install -y gettext-base dos2unix && \
    rm -rf /var/lib/apt/lists/*

# Copy config files
COPY kong.conf /etc/kong/kong.conf
COPY kong.yml /etc/kong/kong.yml.template
COPY docker-entrypoint.sh /docker-entrypoint.sh

# Fix line endings for Windows compatibility
RUN dos2unix /docker-entrypoint.sh /etc/kong/kong.conf /etc/kong/kong.yml.template

# Environment variables
ARG P_VAL=50
ENV P_VALUE=${P_VAL}

# Expose necessary ports
EXPOSE 8000 8443 8001 8444

RUN chmod +x /docker-entrypoint.sh && \
    chown -R kong:kong /etc/kong

USER kong

ENTRYPOINT ["/docker-entrypoint.sh"]