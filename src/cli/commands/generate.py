"""
sing-box configuration generator.

Parse a VLESS URL (vless://...) and integrate its parameters
into a pre-configured sing-box JSON template.
"""

import json
import re
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import parse_qsl, unquote, urlparse

import typer

from cli.models import VlessParams
from cli.ui import console

app = typer.Typer(help="Generate sing-box configurations.", add_completion=False, rich_markup_mode="rich")


def parse_vless_url(url: str) -> VlessParams:
    """
    Parse a standard VLESS invitation URI into a structured Pydantic model.

    Parameters
    ----------
    url : str
        The full 'vless://' connection string.

    Returns
    -------
    VlessParams
        A validated Pydantic model containing all parsed VLESS configuration data.

    Raises
    ------
    ValueError
        If the provided URL does not utilize the 'vless://' scheme.
    """
    parsed = urlparse(url)
    if parsed.scheme != "vless":
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")

    query_params = dict(parse_qsl(parsed.query))

    return VlessParams(
        name=unquote(parsed.fragment) if parsed.fragment else "Unnamed",
        uuid=parsed.username or "",
        server=parsed.hostname or "",
        port=parsed.port or 443,
        **query_params,
    )


def sanitize_filename(name: str) -> str:
    """
    Sanitize an arbitrary server string into a safe, POSIX-compliant filename.

    Parameters
    ----------
    name : str
        The raw configuration or server name containing potential unsafe characters.

    Returns
    -------
    str
        A sanitized, file-system-safe string terminating with '.json'.
    """
    sanitized = re.sub(r"[^\w\s\-.]", "", name)
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = sanitized.strip("_. -")
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized + ".json" if sanitized else "vless_config.json"


def update_vless_outbound(config: dict[str, Any], vless_params: VlessParams) -> None:
    """
    Mutate a sing-box configuration dictionary in-place with VLESS parameters.

    Parameters
    ----------
    config : dict[str, Any]
        The parsed JSON template dictionary for sing-box. Modified in-place.
    vless_params : VlessParams
        The structured data model containing the target VLESS node parameters.

    Raises
    ------
    ValueError
        If no outbound configuration of type 'vless' exists within the template.
    """
    vless_outbound: dict[str, Any] | None = None
    outbounds = cast(list[dict[str, Any]], config.get("outbounds", []))

    for ob in outbounds:
        if ob.get("type") == "vless":
            vless_outbound = ob
            break

    if vless_outbound is None:
        raise ValueError("VLESS outbound not found in the template")

    vless_outbound["server"] = vless_params.server
    vless_outbound["server_port"] = int(vless_params.port)
    vless_outbound["uuid"] = vless_params.uuid
    if vless_params.flow:
        vless_outbound["flow"] = vless_params.flow

    match vless_params.security:
        case "reality":
            tls_config = vless_outbound.setdefault("tls", {})
            tls_config.update({"enabled": True, "server_name": vless_params.sni} if vless_params.sni else {"enabled": True})
            utls_config = tls_config.setdefault("utls", {})
            utls_config.update({"enabled": True, "fingerprint": vless_params.fp})

            reality_config = tls_config.setdefault("reality", {"enabled": True})
            if vless_params.pbk:
                reality_config["public_key"] = vless_params.pbk
            if vless_params.sid:
                reality_config["short_id"] = vless_params.sid

        case "tls":
            tls_config = vless_outbound.setdefault("tls", {})
            tls_config.update({"enabled": True, "server_name": vless_params.sni} if vless_params.sni else {"enabled": True})
            utls_config = tls_config.setdefault("utls", {})
            utls_config.update({"enabled": True, "fingerprint": vless_params.fp})

        case _:
            pass

    match vless_params.type:
        case "ws":
            transport_config = vless_outbound.setdefault("transport", {"type": "ws"})
            ws_config = transport_config.setdefault("ws", {})
            if vless_params.path:
                ws_config["path"] = vless_params.path
            if vless_params.host:
                ws_config["headers"] = {"Host": vless_params.host}
        case "grpc":
            transport_config = vless_outbound.setdefault("transport", {"type": "grpc"})
            if vless_params.path:
                grpc_config = transport_config.setdefault("grpc", {})
                grpc_config["service_name"] = vless_params.path
        case _:
            pass


def generate_config(template_path: Path, vless_url: str, output_path: Path | None = None) -> str:
    """
    Load a sing-box template, inject VLESS parameters, and save the configuration.

    Parameters
    ----------
    template_path : Path
        FileSystem path to the baseline sing-box JSON template file.
    vless_url : str
        The full 'vless://' string containing configuration directives.
    output_path : Path | None, optional
        The file destination path where the generated configuration should be saved.

    Returns
    -------
    str
        The complete, pretty-printed JSON configuration string.

    Raises
    ------
    ValueError
        If parsing the VLESS string, reading the template, or applying modifications fails.
    OSError
        If disk write operations fail for the output path.
    """
    try:
        vless_params = parse_vless_url(vless_url)
        console.print(f"[bold success]Parsed VLESS URL[/bold success] for server: [info]{vless_params.name}[/info]")
        console.print(f"  [muted]Server:[/muted] {vless_params.server}:{vless_params.port}")
        console.print(f"  [muted]UUID:[/muted] {vless_params.uuid}")
        console.print(f"  [muted]Security:[/muted] {vless_params.security}")
    except Exception as e:
        raise ValueError(f"VLESS URL parsing error: {e}") from e

    try:
        config = json.loads(template_path.read_text(encoding="utf-8"))
        console.print(f"[success]Loaded template:[/success] {template_path.name}")
    except Exception as e:
        raise ValueError(f"Template parsing error: {e}") from e

    try:
        update_vless_outbound(config, vless_params)
        console.print("[success]VLESS outbound configuration updated[/success]")
    except Exception as e:
        raise ValueError(f"Configuration update error: {e}") from e

    config_json = json.dumps(config, indent=2, ensure_ascii=False)

    if output_path:
        try:
            output_path.write_text(config_json, encoding="utf-8")
            console.print(
                f"[bold success]Success:[/bold success] Configuration saved to: [info]{output_path.resolve()}[/info]"
            )
        except Exception as e:
            raise OSError(f"File save error: {e}") from e

    return config_json


@app.command("build", help="Inject a [bold green]VLESS[/bold green] connection string into a sing-box JSON template.")
def generate(
    url: Annotated[
        str, typer.Option("--url", help="Raw VLESS connection string (vless://...).", rich_help_panel="Input Parameters")
    ],
    template: Annotated[
        Path,
        typer.Option("--template", help="Path to the baseline sing-box JSON template.", rich_help_panel="Input Parameters"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Explicit path to save the generated config.", rich_help_panel="Output Config"),
    ] = None,
) -> None:
    """
    Compile a sing-box configuration from a VLESS link.

    Parameters
    ----------
    url : str
        The input VLESS invitation connection string.
    template : Path
        The input JSON configuration template file path.
    output : Path | None, optional
        Explicit target file path to save the generated JSON.

    Raises
    ------
    typer.Exit
        Exits with code 1 if the template does not exist or if configuration fails.
    """
    if not template.exists():
        console.print(f"[bold error]Error:[/bold error] Template file not found: {template}")
        raise typer.Exit(code=1)

    try:
        output_path: Path | None = output
        if not output_path:
            vless_params = parse_vless_url(url)
            output_path = Path(sanitize_filename(vless_params.name))

        generate_config(template, url, output_path)

    except Exception as e:
        console.print(f"[bold error]Error:[/bold error] {e}")
        raise typer.Exit(code=1) from e
