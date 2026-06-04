import logging
import os
import re
from dataclasses import dataclass, field

from ldap3 import ALL_ATTRIBUTES, NONE, NTLM, SIMPLE, SUBTREE, Connection, Server
from ldap3.utils.conv import escape_filter_chars


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class LoginConfig:
    ad_domain: str = field(default_factory=lambda: os.environ.get("AD_DOMAIN", "icbv.com"))
    ad_netbios_domain: str = field(
        default_factory=lambda: os.environ.get(
            "AD_NETBIOS_DOMAIN",
            os.environ.get("AD_DOMAIN", "icbv.com").split(".")[0],
        ).upper()
    )
    ad_auth_mode: str = field(default_factory=lambda: os.environ.get("AD_AUTH_MODE", "SIMPLE").upper())
    ad_upn_suffix: str = field(default_factory=lambda: os.environ.get("AD_UPN_SUFFIX", os.environ.get("AD_DOMAIN", "icbv.com")))
    ad_server: str = field(default_factory=lambda: os.environ.get("AD_SERVER", f"ldap://{os.environ.get('AD_DOMAIN', 'icbv.com')}"))
    base_dn: str = field(default_factory=lambda: os.environ.get("BASE_DN", "DC=icbv,DC=com"))
    ad_service_user: str = field(default_factory=lambda: os.environ.get("AD_SERVICE_USER", ""))
    ad_service_pass: str = field(default_factory=lambda: os.environ.get("AD_SERVICE_PASS", ""))
    ma_cb_ad_attribute: str = field(default_factory=lambda: os.environ.get("MA_CB_AD_ATTRIBUTE", "employeeID"))
    ad_debug: bool = field(default_factory=lambda: _env_bool("AD_DEBUG", True))
    ad_connect_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("AD_CONNECT_TIMEOUT_SECONDS", "2"))
    )

    def normalize_login_user(self, user_id):
        user_id = str(user_id or "").strip()
        if "\\" in user_id:
            return user_id.split("\\", 1)[1]
        if "@" in user_id:
            return user_id.split("@", 1)[0]
        return user_id

    def simple_bind_user(self, user_id):
        user_id = str(user_id or "").strip()
        if "@" in user_id or "\\" in user_id:
            return user_id
        return f"{user_id}@{self.ad_upn_suffix}"

    def ntlm_bind_user(self, user_id):
        user_id = str(user_id or "").strip()
        if "\\" in user_id:
            return user_id
        if "@" in user_id:
            user_id = user_id.split("@", 1)[0]
        return f"{self.ad_netbios_domain}\\{user_id}"

    def bind_users(self, user_id):
        if self.ad_auth_mode == "NTLM":
            return [self.ntlm_bind_user(user_id)]
        return [self.simple_bind_user(user_id)]

    def service_bind_user(self):
        if not self.ad_service_user:
            return ""
        if self.ad_auth_mode == "NTLM":
            return self.ntlm_bind_user(self.ad_service_user)
        return self.simple_bind_user(self.ad_service_user)


def setup_ad_logger():
    logger = logging.getLogger("portal_ad_auth")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
    return logger


def mask_user(value):
    value = str(value or "").strip()
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[:2]}***{value[-1:]}"


def get_authentication(config):
    return NTLM if config.ad_auth_mode == "NTLM" else SIMPLE


def serialize_ad_value(value):
    if isinstance(value, (list, tuple, set)):
        return [serialize_ad_value(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    return str(value) if value is not None else ""


def normalize_ad_attributes(entry):
    return {
        key: serialize_ad_value(value)
        for key, value in entry.entry_attributes_as_dict.items()
    }


def find_ma_cb_candidates(ad_extra_info):
    candidates = {}
    for key, value in ad_extra_info.items():
        values = value if isinstance(value, list) else [value]
        matches = []
        for item in values:
            matches.extend(re.findall(r"(?<!\d)\d{8}(?!\d)", str(item or "")))
        if matches:
            candidates[key] = list(dict.fromkeys(matches))
    return candidates


def open_ad_connection(config, logger, user_id=None, password=None):
    server = Server(config.ad_server, get_info=NONE, connect_timeout=config.ad_connect_timeout_seconds)
    authentication = get_authentication(config)

    if config.ad_service_user and config.ad_service_pass:
        service_user = config.service_bind_user()
        logger.info("AD bind with service account | user=%s", mask_user(service_user))
        return Connection(
            server,
            user=service_user,
            password=config.ad_service_pass,
            authentication=authentication,
            auto_bind=True,
        )

    last_error = None
    for bind_user in config.bind_users(user_id):
        try:
            logger.info("AD bind with login user | user=%s", mask_user(bind_user))
            return Connection(
                server,
                user=bind_user,
                password=password,
                authentication=authentication,
                auto_bind=True,
            )
        except Exception as exc:
            last_error = exc
            logger.exception("AD bind failed | user=%s | error=%s", mask_user(bind_user), str(exc))

    raise last_error or RuntimeError("Khong tao duoc ket noi AD")


def validate_ad_user(config, logger, user_id, password):
    try:
        server = Server(config.ad_server, get_info=NONE, connect_timeout=config.ad_connect_timeout_seconds)
        authentication = get_authentication(config)
        last_error = None
        conn = None

        for bind_user in config.bind_users(user_id):
            try:
                conn = Connection(
                    server,
                    user=bind_user,
                    password=password,
                    authentication=authentication,
                    auto_bind=True,
                )
                break
            except Exception as exc:
                last_error = exc
                logger.exception("Credential bind failed | user=%s | error=%s", mask_user(bind_user), str(exc))

        if conn is None:
            raise last_error or RuntimeError("Khong xac thuc duoc user AD")

        conn.unbind()
        return True, ""
    except Exception as exc:
        logger.exception("Credential validation failed | user=%s | error=%s", mask_user(user_id), str(exc))
        return False, str(exc)


def get_user_groups_from_ad(config, logger, user_id, password=None):
    try:
        conn = open_ad_connection(config, logger, user_id, password)
        search_user = config.normalize_login_user(user_id)
        safe_user_id = escape_filter_chars(search_user)
        search_filter = f"(sAMAccountName={safe_user_id})"
        conn.search(
            search_base=config.base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=ALL_ATTRIBUTES,
        )

        if not conn.entries:
            conn.unbind()
            return [], {}, "Khong tim thay user trong AD"

        entry = conn.entries[0]
        member_of = entry.memberOf.values if "memberOf" in entry else []
        group_names = []
        for group_dn in member_of:
            group_dn = str(group_dn)
            if group_dn.upper().startswith("CN="):
                group_names.append(group_dn.split(",", 1)[0][3:].strip())

        ad_extra_info = normalize_ad_attributes(entry)
        conn.unbind()
        return group_names, ad_extra_info, ""
    except Exception as exc:
        logger.exception("Group lookup failed | user=%s | error=%s", mask_user(user_id), str(exc))
        return [], {}, str(exc)
