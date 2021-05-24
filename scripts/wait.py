import logging
import logging.config
import os

from pygluu.containerlib import get_manager
from pygluu.containerlib import wait_for
from pygluu.containerlib.validators import validate_persistence_type
from pygluu.containerlib.validators import validate_persistence_ldap_mapping
from pygluu.containerlib.validators import validate_persistence_sql_dialect


from settings import LOGGING_CONFIG

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("wait")


def main():
    persistence_type = os.environ.get("GLUU_PERSISTENCE_TYPE", "ldap")
    validate_persistence_type(persistence_type)

    ldap_mapping = os.environ.get("GLUU_PERSISTENCE_LDAP_MAPPING", "default")
    validate_persistence_ldap_mapping(persistence_type, ldap_mapping)

    if persistence_type == "sql":
        sql_dialect = os.environ.get("GLUU_SQL_DB_DIALECT", "mysql")
        validate_persistence_sql_dialect(sql_dialect)

    manager = get_manager()
    deps = ["config", "secret"]

    if persistence_type == "hybrid":
        deps += ["ldap", "couchbase"]
    else:
        deps.append(persistence_type)

    deps.append("oxauth")
    deps.append("oxd")
    wait_for(manager, deps)


if __name__ == "__main__":
    main()
