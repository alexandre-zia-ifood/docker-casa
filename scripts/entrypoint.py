import os
import re

from pygluu.containerlib import get_manager
from pygluu.containerlib.persistence import render_couchbase_properties
from pygluu.containerlib.persistence import render_gluu_properties
from pygluu.containerlib.persistence import render_hybrid_properties
from pygluu.containerlib.persistence import render_ldap_properties
from pygluu.containerlib.persistence import render_salt
from pygluu.containerlib.persistence import sync_couchbase_truststore
from pygluu.containerlib.persistence import sync_ldap_truststore
from pygluu.containerlib.persistence import render_sql_properties
from pygluu.containerlib.persistence import render_spanner_properties
from pygluu.containerlib.utils import cert_to_truststore
from pygluu.containerlib.utils import get_server_certificate
from pygluu.containerlib.utils import as_boolean

from casa_config import CasaConfig
from oxd import get_oxd_cert

manager = get_manager()


def modify_webdefault_xml():
    fn = "/opt/jetty/etc/webdefault.xml"
    with open(fn) as f:
        txt = f.read()

    # disable dirAllowed
    updates = re.sub(
        r'(<param-name>dirAllowed</param-name>)(\s*)(<param-value>)true(</param-value>)',
        r'\1\2\3false\4',
        txt,
        flags=re.DOTALL | re.M,
    )

    with open(fn, "w") as f:
        f.write(updates)


def modify_jetty_xml():
    fn = "/opt/jetty/etc/jetty.xml"
    with open(fn) as f:
        txt = f.read()

    # disable contexts
    updates = re.sub(
        r'<New id="DefaultHandler" class="org.eclipse.jetty.server.handler.DefaultHandler"/>',
        r'<New id="DefaultHandler" class="org.eclipse.jetty.server.handler.DefaultHandler">\n\t\t\t\t <Set name="showContexts">false</Set>\n\t\t\t </New>',
        txt,
        flags=re.DOTALL | re.M,
    )

    # disable Jetty version info
    updates = re.sub(
        r'(<Set name="sendServerVersion"><Property name="jetty.httpConfig.sendServerVersion" deprecated="jetty.send.server.version" default=")true(" /></Set>)',
        r'\1false\2',
        updates,
        flags=re.DOTALL | re.M,
    )

    with open(fn, "w") as f:
        f.write(updates)


def main():
    persistence_type = os.environ.get("GLUU_PERSISTENCE_TYPE", "ldap")

    render_salt(manager, "/app/templates/salt.tmpl", "/etc/gluu/conf/salt")
    render_gluu_properties("/app/templates/gluu.properties.tmpl", "/etc/gluu/conf/gluu.properties")

    if persistence_type in ("ldap", "hybrid"):
        render_ldap_properties(
            manager,
            "/app/templates/gluu-ldap.properties.tmpl",
            "/etc/gluu/conf/gluu-ldap.properties",
        )
        sync_ldap_truststore(manager)

    if persistence_type in ("couchbase", "hybrid"):
        render_couchbase_properties(
            manager,
            "/app/templates/gluu-couchbase.properties.tmpl",
            "/etc/gluu/conf/gluu-couchbase.properties",
        )
        sync_couchbase_truststore(manager)

    if persistence_type == "hybrid":
        render_hybrid_properties("/etc/gluu/conf/gluu-hybrid.properties")

    if persistence_type == "sql":
        render_sql_properties(
            manager,
            "/app/templates/gluu-sql.properties.tmpl",
            "/etc/gluu/conf/gluu-sql.properties",
        )

    if persistence_type == "spanner":
        render_spanner_properties(
            manager,
            "/app/templates/gluu-spanner.properties.tmpl",
            "/etc/gluu/conf/gluu-spanner.properties",
        )

    if not os.path.isfile("/etc/certs/gluu_https.crt"):
        if as_boolean(os.environ.get("GLUU_SSL_CERT_FROM_SECRETS", False)):
            manager.secret.to_file("ssl_cert", "/etc/certs/gluu_https.crt")
        else:
            get_server_certificate(manager.config.get("hostname"), 443, "/etc/certs/gluu_https.crt")

    cert_to_truststore(
        "gluu_https",
        "/etc/certs/gluu_https.crt",
        "/usr/lib/jvm/default-jvm/jre/lib/security/cacerts",
        "changeit",
    )

    get_oxd_cert()
    cert_to_truststore(
        "gluu_oxd",
        "/etc/certs/oxd.crt",
        "/usr/lib/jvm/default-jvm/jre/lib/security/cacerts",
        "changeit",
    )
    modify_jetty_xml()
    modify_webdefault_xml()

    manager.secret.to_file("passport_rp_jks_base64", "/etc/certs/passport-rp.jks",
                           decode=True, binary_mode=True)

    config = CasaConfig(manager)
    config.setup()


if __name__ == "__main__":
    main()
