FROM alpine:3.13

# ===============
# Alpine packages
# ===============

RUN apk update \
    && apk add --no-cache py3-pip openssl tini openjdk11-jre-headless py3-cryptography py3-lxml py3-grpcio py3-psycopg2 \
    && apk add --no-cache --virtual build-deps git wget gcc musl-dev python3-dev libffi-dev openssl-dev libxml2-dev libxslt-dev cargo \
    && mkdir -p /usr/java/latest \
    && ln -sf /usr/lib/jvm/default-jvm/jre /usr/java/latest/jre

# =====
# Jetty
# =====

ARG JETTY_VERSION=9.4.43.v20210629
ARG JETTY_HOME=/opt/jetty
ARG JETTY_BASE=/opt/gluu/jetty
ARG JETTY_USER_HOME_LIB=/home/jetty/lib

# Install jetty
RUN wget -q https://repo1.maven.org/maven2/org/eclipse/jetty/jetty-distribution/${JETTY_VERSION}/jetty-distribution-${JETTY_VERSION}.tar.gz -O /tmp/jetty.tar.gz \
    && mkdir -p /opt \
    && tar -xzf /tmp/jetty.tar.gz -C /opt \
    && mv /opt/jetty-distribution-${JETTY_VERSION} ${JETTY_HOME} \
    && rm -rf /tmp/jetty.tar.gz

# Ports required by jetty
EXPOSE 8080

# ====
# Casa
# ====

ENV GLUU_VERSION=4.3.0-SNAPSHOT
ENV GLUU_BUILD_DATE="2021-08-08 14:25"

# Install Casa
RUN wget -q https://ox.gluu.org/maven/org/gluu/casa/${GLUU_VERSION}/casa-${GLUU_VERSION}.war -O /tmp/casa.war \
    && mkdir -p ${JETTY_BASE}/casa/webapps/casa \
    && unzip -qq /tmp/casa.war -d ${JETTY_BASE}/casa/webapps/casa \
    && java -jar ${JETTY_HOME}/start.jar jetty.home=${JETTY_HOME} jetty.base=${JETTY_BASE}/casa --add-to-start=server,deploy,resources,http,http-forwarded,jsp \
    && rm -f /tmp/casa.war

# ===========
# Custom libs
# ===========

RUN mkdir -p /usr/share/java

ARG TWILIO_VERSION=7.17.0
RUN wget -q https://repo1.maven.org/maven2/com/twilio/sdk/twilio/${TWILIO_VERSION}/twilio-${TWILIO_VERSION}.jar -O /usr/share/java/twilio.jar

ARG JSMPP_VERSION=2.3.7
RUN wget -q https://repo1.maven.org/maven2/org/jsmpp/jsmpp/${JSMPP_VERSION}/jsmpp-${JSMPP_VERSION}.jar -O /usr/share/java/jsmpp.jar

# ======
# Python
# ======

COPY requirements.txt /app/requirements.txt
RUN pip3 install -U pip \
    && pip3 install --no-cache-dir -r /app/requirements.txt \
    && rm -rf /src/pygluu-containerlib/.git

# =======
# Cleanup
# =======

RUN apk del build-deps \
    && rm -rf /var/cache/apk/*

# =======
# License
# =======

RUN mkdir -p /licenses
COPY LICENSE /licenses/

# ==========
# Config ENV
# ==========

ENV GLUU_CONFIG_ADAPTER=consul \
    GLUU_CONFIG_CONSUL_HOST=localhost \
    GLUU_CONFIG_CONSUL_PORT=8500 \
    GLUU_CONFIG_CONSUL_CONSISTENCY=stale \
    GLUU_CONFIG_CONSUL_SCHEME=http \
    GLUU_CONFIG_CONSUL_VERIFY=false \
    GLUU_CONFIG_CONSUL_CACERT_FILE=/etc/certs/consul_ca.crt \
    GLUU_CONFIG_CONSUL_CERT_FILE=/etc/certs/consul_client.crt \
    GLUU_CONFIG_CONSUL_KEY_FILE=/etc/certs/consul_client.key \
    GLUU_CONFIG_CONSUL_TOKEN_FILE=/etc/certs/consul_token \
    GLUU_CONFIG_KUBERNETES_NAMESPACE=default \
    GLUU_CONFIG_KUBERNETES_CONFIGMAP=gluu \
    GLUU_CONFIG_KUBERNETES_USE_KUBE_CONFIG=false

# ==========
# Secret ENV
# ==========

ENV GLUU_SECRET_ADAPTER=vault \
    GLUU_SECRET_VAULT_SCHEME=http \
    GLUU_SECRET_VAULT_HOST=localhost \
    GLUU_SECRET_VAULT_PORT=8200 \
    GLUU_SECRET_VAULT_VERIFY=false \
    GLUU_SECRET_VAULT_ROLE_ID_FILE=/etc/certs/vault_role_id \
    GLUU_SECRET_VAULT_SECRET_ID_FILE=/etc/certs/vault_secret_id \
    GLUU_SECRET_VAULT_CERT_FILE=/etc/certs/vault_client.crt \
    GLUU_SECRET_VAULT_KEY_FILE=/etc/certs/vault_client.key \
    GLUU_SECRET_VAULT_CACERT_FILE=/etc/certs/vault_ca.crt \
    GLUU_SECRET_KUBERNETES_NAMESPACE=default \
    GLUU_SECRET_KUBERNETES_SECRET=gluu \
    GLUU_SECRET_KUBERNETES_USE_KUBE_CONFIG=false

# ===============
# Persistence ENV
# ===============

ENV GLUU_PERSISTENCE_TYPE=ldap \
    GLUU_PERSISTENCE_LDAP_MAPPING=default \
    GLUU_LDAP_URL=localhost:1636 \
    GLUU_LDAP_USE_SSL=true \
    GLUU_COUCHBASE_URL=localhost \
    GLUU_COUCHBASE_USER=admin \
    GLUU_COUCHBASE_CERT_FILE=/etc/certs/couchbase.crt \
    GLUU_COUCHBASE_PASSWORD_FILE=/etc/gluu/conf/couchbase_password \
    GLUU_COUCHBASE_CONN_TIMEOUT=10000 \
    GLUU_COUCHBASE_CONN_MAX_WAIT=20000 \
    GLUU_COUCHBASE_BUCKET_PREFIX=gluu \
    GLUU_COUCHBASE_TRUSTSTORE_ENABLE=true \
    GLUU_COUCHBASE_KEEPALIVE_INTERVAL=30000 \
    GLUU_COUCHBASE_KEEPALIVE_TIMEOUT=2500 \
    GLUU_SQL_DB_DIALECT=mysql \
    GLUU_SQL_DB_HOST=localhost \
    GLUU_SQL_DB_PORT=3306 \
    GLUU_SQL_DB_NAME=gluu \
    GLUU_SQL_DB_USER=gluu \
    GLUU_SQL_PASSWORD_FILE=/etc/gluu/conf/sql_password \
    GLUU_GOOGLE_SPANNER_INSTANCE_ID="" \
    GLUU_GOOGLE_SPANNER_DATABASE_ID=""

# ===========
# Generic ENV
# ===========

ENV GLUU_MAX_RAM_PERCENTAGE=75.0 \
    GLUU_WAIT_MAX_TIME=300 \
    GLUU_WAIT_SLEEP_DURATION=10 \
    GLUU_OXD_SERVER_URL=https://localhost:8443 \
    GLUU_OXAUTH_BACKEND=localhost:8081 \
    GLUU_JAVA_OPTIONS="" \
    GLUU_DOCUMENT_STORE_TYPE=LOCAL \
    GLUU_JACKRABBIT_URL=http://localhost:8080 \
    GLUU_JACKRABBIT_ADMIN_ID=admin \
    GLUU_JACKRABBIT_ADMIN_PASSWORD_FILE=/etc/gluu/conf/jackrabbit_admin_password \
    GLUU_SSL_CERT_FROM_SECRETS=false \
    GOOGLE_APPLICATION_CREDENTIALS=/etc/gluu/conf/google-credentials.json \
    GOOGLE_PROJECT_ID=""

# ==========
# misc stuff
# ==========

LABEL name="Casa" \
    maintainer="Gluu Inc. <support@gluu.org>" \
    vendor="Gluu Federation" \
    version="4.3.0" \
    release="b1" \
    summary="Gluu Casa" \
    description="Self-service portal for people to manage their account security preferences in the Gluu Server, like 2FA"

RUN mkdir -p /etc/certs \
    /etc/gluu/conf/casa \
    /opt/gluu/python/libs \
    /opt/gluu/jetty/casa/static \
    /opt/gluu/jetty/casa/plugins \
    /deploy \
    /app/templates \
    /app/tmp

COPY templates /app/templates/
COPY scripts /app/scripts
RUN chmod +x /app/scripts/entrypoint.sh \
    && cp /app/templates/casa_web_resources.xml /opt/gluu/jetty/casa/webapps/

ENTRYPOINT ["tini", "-e", "143", "-g", "--"]
CMD ["sh", "/app/scripts/entrypoint.sh"]
