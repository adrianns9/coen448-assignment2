FROM kong:latest

USER root

RUN apt-get update && \
    apt-get install -y gettext-base && \
    rm -rf /var/lib/apt/lists/*

COPY kong.conf /etc/kong/kong.conf
COPY kong.yml /etc/kong/kong.yml.template
COPY docker-entrypoint.sh /docker-entrypoint.sh

ARG P_VAL=50
ENV P_VALUE=${P_VAL}

EXPOSE 8000 8443 8001 8444

RUN sed -i 's/\r$//' /docker-entrypoint.sh && \
    chmod +x /docker-entrypoint.sh && \
    chown -R kong:kong /etc/kong

USER kong

ENTRYPOINT ["/docker-entrypoint.sh"]