"""
sing-box subscription fetcher.

Provide functionality to download subscription links either from a raw source
or a source requiring authentication using an auto-detected system HWID.
"""

import base64
import platform
import subprocess
from pathlib import Path
from typing import Annotated

import httpx
import typer

from cli.ui import console

app = typer.Typer(help="Fetch and manage VLESS subscriptions.", add_completion=False, rich_markup_mode="rich")


def get_hwid() -> str:
    """
    Retrieve the system-specific Hardware Identifier (HWID).

    This function detects the underlying operating system and extracts a unique
    machine identifier. On Linux, it reads from '/etc/machine-id'. On Windows,
    it securely queries the 'MachineGuid' from the Windows Registry.

    Returns
    -------
    str
        The unique hardware identifier string stripped of whitespace.

    Raises
    ------
    RuntimeError
        If the OS is unsupported, or if the respective system files/registry
        keys cannot be accessed or read.
    """
    system: str = platform.system()

    match system:
        case "Linux":
            path = Path("/etc/machine-id")
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
            raise RuntimeError("The /etc/machine-id file was not found.")

        case "Windows":
            try:
                cmd = ["reg", "query", r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"]
                output = subprocess.check_output(cmd, text=True)  # noqa: S603
                return output.split("REG_SZ")[1].strip()
            except Exception as e:
                raise RuntimeError(f"Failed to retrieve Windows HWID: {e}") from e

        case _:
            raise RuntimeError(f"Unsupported platform for automatic HWID detection: {system}")


def fetch_subscription(url: str, hwid: str | None = None) -> str:
    """
    Fetch and decode a subscription payload from a remote provider.

    Executes an HTTP GET request to the specified URL. If an HWID is provided,
    it is injected into the 'X-HWID' HTTP header. Automatically corrects missing
    Base64 padding.

    Parameters
    ----------
    url : str
        The remote endpoint URL hosting the subscription data.
    hwid : str | None, optional
        The system Hardware ID for provider authentication, by default None.

    Returns
    -------
    str
        The decoded plaintext content of the subscription. Returns the raw
        content if Base64 decoding fails.

    Raises
    ------
    ValueError
        If a network timeout occurs, the connection is refused, or the
        server returns a non-2xx HTTP status code.
    """
    headers = {"User-Agent": "sing-box-fetcher/1.0"}
    if hwid:
        headers["X-HWID"] = hwid

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            content: str = response.text.strip()
    except httpx.RequestError as e:
        raise ValueError(f"Network error while requesting {e.request.url!r}.") from e
    except httpx.HTTPStatusError as e:
        raise ValueError(f"HTTP error {e.response.status_code} while requesting {e.request.url!r}.") from e

    try:
        padded_content = content + "=" * (-len(content) % 4)
        decoded_bytes = base64.b64decode(padded_content)
        return decoded_bytes.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return content


def extract_vless_links(content: str) -> list[str]:
    """
    Parse raw subscription text content and extract valid VLESS links.

    Parameters
    ----------
    content : str
        The raw, unparsed text string containing potential subscription links.

    Returns
    -------
    list[str]
        A list of valid, stripped VLESS configuration strings found in the content.
    """
    return [line.strip() for line in content.splitlines() if line.strip().startswith("vless://")]


@app.command("get", help="Fetch and decode [bold green]VLESS[/bold green] links from a subscription URL.")
def fetch(
    url: Annotated[str, typer.Option("--url", help="Remote subscription endpoint URL.", rich_help_panel="Network Options")],
    output: Annotated[
        Path | None, typer.Option("--output", help="Path to save the extracted links.", rich_help_panel="Output Options")
    ] = None,
    raw: Annotated[
        bool, typer.Option("--raw", help="Fetch as an unauthenticated raw source.", rich_help_panel="Authentication Options")
    ] = False,
    hwid: Annotated[
        bool,
        typer.Option(
            "--hwid", help="Inject system Hardware ID (HWID) for authentication.", rich_help_panel="Authentication Options"
        ),
    ] = False,
) -> None:
    """
    Fetch, decode, and save VLESS subscription links.

    Parameters
    ----------
    url : str
        The remote subscription endpoint URL.
    output : Path | None, optional
        The file system path where extracted links will be saved.
        Defaults to 'vless_links.txt' if not provided.
    raw : bool, optional
        Flag to fetch the subscription without hardware authentication.
        Defaults to False.
    hwid : bool, optional
        Flag to fetch the subscription using the local machine's hardware ID.
        Defaults to False.

    Raises
    ------
    typer.Exit
        Exits with code 1 if argument validation fails (e.g., missing authentication method),
        or if network/disk errors occur during the process.
    """
    if output is None:
        output = Path("vless_links.txt")

    if not raw and not hwid:
        console.print("[bold error]Error:[/bold error] You must specify either --raw or --hwid.")
        raise typer.Exit(code=1)
    if raw and hwid:
        console.print("[bold error]Error:[/bold error] --raw and --hwid are mutually exclusive.")
        raise typer.Exit(code=1)

    target_hwid = None
    if hwid:
        try:
            target_hwid = get_hwid()
            console.print(f"[bold info]Info:[/bold info] Detected system HWID: [success]{target_hwid}[/success]")
        except RuntimeError as e:
            console.print(f"[bold error]Error:[/bold error] {e}")
            raise typer.Exit(code=1) from e

    mode = "HWID" if hwid else "RAW"
    console.print(f"Fetching in [bold primary]{mode}[/bold primary] mode from: [info]{url}[/info]")

    try:
        raw_content = fetch_subscription(url, hwid=target_hwid)
        vless_links = extract_vless_links(raw_content)

        if not vless_links:
            console.print("[bold warning]Warning:[/bold warning] No VLESS links found in the subscription.")
            raise typer.Exit(code=1)

        output.write_text("\n".join(vless_links) + "\n", encoding="utf-8")
        console.print(f"[bold success]Success:[/bold success] Extracted {len(vless_links)} VLESS links.")
        console.print(f"Links saved to: [info]{output.resolve()}[/info]")

    except ValueError as e:
        console.print(f"[bold error]Network Error:[/bold error] {e}")
        raise typer.Exit(code=1) from e
    except OSError as e:
        console.print(f"[bold error]Write Error:[/bold error] {e}")
        raise typer.Exit(code=1) from e
