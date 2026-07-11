"""
VLESS configuration models.

Provides Pydantic data models for parsing and validating VLESS
invitation URIs and subscription metadata.
"""

from pydantic import BaseModel, ConfigDict, Field


class VlessParams(BaseModel):
    """
    Represent a validated VLESS connection configuration.

    Attributes
    ----------
    name : str
        Human-readable name of the node.
    uuid : str
        User authentication UUID.
    server : str
        Target server hostname or IP address.
    port : int
        Connection port.
    security : str
        Transport layer security mode. Defaults to 'none'.
    encryption : str
        Encryption type. Defaults to 'none'.
    header_type : str
        Packet header specification. Defaults to 'none'.
    fp : str
        TLS fingerprint. Defaults to 'chrome'.
    type : str
        Network connection type (tcp, ws, etc.). Defaults to 'tcp'.
    flow : str
        Flow control protocol identifier.
    pbk : str
        Public key for reality protocol.
    sni : str
        Server Name Indication.
    sid : str
        Short ID for reality.
    path : str
        Transport path.
    host : str
        Target host.
    alpn : str
        ALPN values.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    uuid: str
    server: str
    port: int
    security: str = "none"
    encryption: str = "none"
    header_type: str = Field(default="none", alias="headerType")
    fp: str = "chrome"
    type: str = "tcp"
    flow: str = ""
    pbk: str = ""
    sni: str = ""
    sid: str = ""
    path: str = ""
    host: str = ""
    alpn: str = ""
