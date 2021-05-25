import os
import json
from collections import namedtuple

from pygluu.containerlib.persistence.couchbase import CouchbaseClient
from pygluu.containerlib.persistence.couchbase import get_couchbase_password
from pygluu.containerlib.persistence.couchbase import get_couchbase_user
from pygluu.containerlib.persistence.ldap import LdapClient
from pygluu.containerlib.persistence.sql import SQLClient
from pygluu.containerlib.persistence.spanner import SpannerClient

from oxd import resolve_oxd_url

Entry = namedtuple("Entry", ["id", "attrs"])


class LDAPBackend:
    def __init__(self, manager):
        self.client = LdapClient(manager)
        self.manager = manager

    def get_entry(self, key, filter_="", attrs=None, **kwargs):
        filter_ = filter_ or "(objectClass=*)"
        entry = self.client.get(key, filter_, attrs)

        _attrs = {}
        for k, v in entry.entry_attributes_as_dict.items():
            if len(v) < 2:
                v = v[0]
            _attrs[k] = v
        return Entry(entry.entry_dn, _attrs)

    def modify_entry(self, key, attrs=None, **kwargs):
        attrs = attrs or {}
        del_flag = kwargs.get("delete_attr", False)

        if del_flag:
            mod = self.client.MODIFY_DELETE
        else:
            mod = self.client.MODIFY_REPLACE

        for k, v in attrs.items():
            if not isinstance(v, list):
                v = [v]
            attrs[k] = [(mod, v)]
        return self.client.modify(key, attrs)

    def add_entry(self, key, attrs=None, **kwargs):
        attrs = attrs or {}

        for k, v in attrs.items():
            if not isinstance(v, list):
                v = [v]
            attrs[k] = v
        return self.client.add(key, attrs)


class CouchbaseBackend:
    def __init__(self, manager):
        hosts = os.environ.get("GLUU_COUCHBASE_URL", "localhost")
        user = get_couchbase_user(manager)
        password = get_couchbase_password(manager)
        self.client = CouchbaseClient(hosts, user, password)

    def get_entry(self, key, filter_="", attrs=None, **kwargs):
        bucket = kwargs.get("bucket")
        req = self.client.exec_query(
            "SELECT META().id, {0}.* FROM {0} USE KEYS '{1}'".format(bucket, key)
        )

        if not req.ok:
            return

        try:
            attrs = req.json()["results"][0]
            return Entry(attrs.pop("id"), attrs)
        except IndexError:
            return

    def modify_entry(self, key, attrs=None, **kwargs):
        attrs = attrs or {}
        bucket = kwargs.get("bucket")
        del_flag = kwargs.get("delete_attr", False)

        if del_flag:
            mod_kv = "UNSET {}".format(
                ",".join([k for k, _ in attrs.items()])
            )
        else:
            mod_kv = "SET {}".format(
                ",".join(["{}={}".format(k, json.dumps(v)) for k, v in attrs.items()])
            )

        query = "UPDATE {} USE KEYS '{}' {}".format(bucket, key, mod_kv)
        req = self.client.exec_query(query)
        if req.ok:
            resp = req.json()
            return bool(resp["status"] == "success"), resp["status"]
        return False, ""

    def add_entry(self, key, attrs=None, **kwargs):
        attrs = attrs or {}
        bucket = kwargs.get("bucket")

        query = 'INSERT INTO `%s` (KEY, VALUE) VALUES ("%s", %s);\n' % (bucket, key, json.dumps(attrs))
        req = self.client.exec_query(query)

        if req.ok:
            resp = req.json()
            return bool(resp["status"] == "success"), resp["status"]
        return False, ""


class SQLBackend:
    def __init__(self, manager):
        self.client = SQLClient()

    def get_entry(self, key, filter_="", attrs=None, **kwargs):
        entry = self.client.get("oxApplicationConfiguration", key)

        if not entry:
            return {}
        return Entry(entry.pop("doc_id"), entry)

    def modify_entry(self, key, attrs=None, **kwargs):
        attrs = attrs or {}
        updated = self.client.update("oxApplicationConfiguration", key, attrs)
        return updated, ""

    def add_entry(self, key, attrs=None, **kwargs):
        attrs = attrs or {}
        self.client.insert_into("oxApplicationConfiguration", attrs)
        return True, ""


class SpannerBackend(SQLBackend):
    def __init__(self, manager):
        self.client = SpannerClient()


_backend_classes = {
    "ldap": LDAPBackend,
    "couchbase": CouchbaseBackend,
    "sql": SQLBackend,
    "spanner": SpannerBackend,
}


class CasaConfig(object):
    def __init__(self, manager):
        self.manager = manager

        persistence_type = os.environ.get("GLUU_PERSISTENCE_TYPE", "ldap")
        ldap_mapping = os.environ.get("GLUU_PERSISTENCE_LDAP_MAPPING", "default")

        if persistence_type in ("ldap", "couchbase", "sql", "spanner"):
            backend_type = persistence_type
        else:  # probably `hybrid`
            if ldap_mapping == "default":
                backend_type = "ldap"
            else:
                backend_type = "couchbase"

        self.backend_type = backend_type
        self.backend = _backend_classes[backend_type](self.manager)

    def json_from_template(self):
        oxd_url = os.environ.get("GLUU_OXD_SERVER_URL", "localhost:8443")

        src = "/app/templates/casa.json"

        _, oxd_host, oxd_port = resolve_oxd_url(oxd_url)
        ctx = {
            "hostname": self.manager.config.get("hostname"),
            "oxd_hostname": oxd_host,
            "oxd_port": oxd_port,
        }

        with open(src) as fr:
            return json.loads(fr.read() % ctx)

    def setup(self):
        data = self.json_from_template()

        if self.backend_type == "ldap":
            key = "ou=casa,ou=configuration,o=gluu"
        elif self.backend_type == "couchbase":
            key = "configuration_casa"
        else:
            # likely sql or spanner
            key = "casa"

        bucket_prefix = os.environ.get("GLUU_COUCHBASE_BUCKET_PREFIX", "gluu")

        config = self.backend.get_entry(key, **{"bucket": bucket_prefix})

        if not config:
            conf_app = data

            if self.backend_type == "ldap":
                attrs = {
                    "objectClass": ["top", "oxApplicationConfiguration"],
                    "ou": "casa",
                    "oxConfApplication": json.dumps(data),
                    "oxRevision": "1",
                }
            elif self.backend_type == "couchbase":
                attrs = {
                    "dn": "ou=casa,ou=configuration,o=gluu",
                    "objectClass": "oxApplicationConfiguration",
                    "ou": "casa",
                    "oxConfApplication": data,
                    "oxRevision": 1,
                }
            else:
                # likely sql or spanner
                attrs = {
                    "dn": "ou=casa,ou=configuration,o=gluu",
                    "objectClass": "oxApplicationConfiguration",
                    "ou": "casa",
                    "oxConfApplication": json.dumps(data),
                    "oxRevision": 1,
                }
            self.backend.add_entry(key, attrs, **{"bucket": bucket_prefix})

        # if config exists, modify it if neccessary
        else:
            # compare oxd_config
            should_modify = False

            conf_app = config.attrs["oxConfApplication"]
            if self.backend_type != "couchbase":
                conf_app = json.loads(conf_app)

            if data["oxd_config"]["host"] != conf_app["oxd_config"]["host"]:
                conf_app["oxd_config"]["host"] = data["oxd_config"]["host"]
                should_modify = True

            if data["oxd_config"]["port"] != conf_app["oxd_config"]["port"]:
                conf_app["oxd_config"]["port"] = data["oxd_config"]["port"]
                should_modify = True

            if not should_modify:
                return

            if self.backend_type != "couchbase":
                conf_app = json.dumps(conf_app)

            attrs = {"oxConfApplication": conf_app}
            self.backend.modify_entry(config.id, attrs, **{"bucket": bucket_prefix})
