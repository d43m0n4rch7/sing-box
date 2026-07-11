"""
sing-box JSON ↔ BPF profile converter.

Provide bidirectional conversion between standard JSON configuration files
and the sing-box binary profile format (BPF).
"""

import gzip
import io
import struct
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from cli.models import MessageType, ProfileContent, ProfileType, ProfileTypeArg
from cli.ui import console

app = typer.Typer(help="sing-box JSON ↔ BPF profile converter.", add_completion=False, rich_markup_mode="rich")


def write_uvarint(writer: io.BytesIO, value: int) -> int:
    """
    Encode an unsigned integer into a Uvarint byte sequence.

    Parameters
    ----------
    writer : io.BytesIO
        The active byte stream buffer where the encoded data will be written.
    value : int
        The positive integer to encode.

    Returns
    -------
    int
        The total number of bytes written to the buffer.
    """
    written = 0
    while value >= 0x80:
        writer.write(struct.pack("B", (value & 0x7F) | 0x80))
        value >>= 7
        written += 1
    writer.write(struct.pack("B", value & 0x7F))
    return written + 1


def read_uvarint(reader: io.BytesIO) -> int:
    """
    Decode an unsigned variable-length integer (Uvarint) from a byte stream.

    Parameters
    ----------
    reader : io.BytesIO
        The active byte stream buffer containing Uvarint-encoded data.

    Returns
    -------
    int
        The fully reconstructed positive integer.

    Raises
    ------
    ValueError
        If the stream ends prematurely or shifts overflow the 64-bit threshold.
    """
    value = 0
    shift = 0
    while True:
        byte = reader.read(1)
        if not byte:
            raise ValueError("Unexpected end of data while reading uvarint")
        b = byte[0]
        value |= (b & 0x7F) << shift
        if b & 0x80 == 0:
            break
        shift += 7
        if shift >= 64:
            raise ValueError("Uvarint value is too large")
    return value


def write_varbin_string(writer: io.BytesIO, value: str) -> None:
    """
    Encode and write a string into a stream prefixed by its Uvarint length.

    Parameters
    ----------
    writer : io.BytesIO
        The target binary stream buffer.
    value : str
        The text string to serialize.
    """
    encoded = value.encode(encoding="utf-8")
    write_uvarint(writer, len(encoded))
    if encoded:
        writer.write(encoded)


def read_varbin_string(reader: io.BytesIO) -> str:
    """
    Read and decode a length-prefixed UTF-8 string from a byte stream.

    Parameters
    ----------
    reader : io.BytesIO
        The source binary stream buffer.

    Returns
    -------
    str
        The decoded UTF-8 string.

    Raises
    ------
    ValueError
        If the available bytes in the reader do not match the expected length.
    """
    length = read_uvarint(reader)
    data = reader.read(length)
    if len(data) != length:
        raise ValueError(f"Failed to read string of length {length}")
    return data.decode("utf-8")


def encode_profile_content(profile: ProfileContent) -> bytes:
    """
    Serialize a ProfileContent model into a compressed Binary Profile Format (BPF).

    Parameters
    ----------
    profile : ProfileContent
        The populated profile data model to serialize.

    Returns
    -------
    bytes
        The fully constructed, GZIP-compressed BPF byte string ready for I/O.
    """
    buffer = io.BytesIO()
    buffer.write(struct.pack("B", MessageType.PROFILE_CONTENT.value))
    buffer.write(struct.pack("B", 1))

    compressed_buffer = io.BytesIO()

    with gzip.GzipFile(fileobj=compressed_buffer, mode="wb") as gzip_writer:
        inner_buffer = io.BytesIO()
        write_varbin_string(inner_buffer, profile.name)
        inner_buffer.write(struct.pack(">i", profile.profile_type.value))
        write_varbin_string(inner_buffer, profile.config)

        if profile.profile_type != ProfileType.LOCAL:
            write_varbin_string(inner_buffer, profile.remote_path)

        if profile.profile_type == ProfileType.REMOTE:
            inner_buffer.write(struct.pack("?", profile.auto_update))
            inner_buffer.write(struct.pack(">i", profile.auto_update_interval))
            inner_buffer.write(struct.pack(">q", profile.last_updated))

        gzip_writer.write(inner_buffer.getvalue())

    buffer.write(compressed_buffer.getvalue())
    return buffer.getvalue()


def decode_bpf(data: bytes) -> ProfileContent:
    """
    Deserialize a compressed Binary Profile Format (BPF) byte array into a ProfileContent model.

    Parameters
    ----------
    data : bytes
        The raw binary data representing a compiled BPF profile.

    Returns
    -------
    ProfileContent
        A fully reconstructed Pydantic model populated with the profile metadata.

    Raises
    ------
    ValueError
        If the byte layout is empty, header is invalid, or decompression fails.
    """
    if not data:
        raise ValueError("Empty BPF data")

    reader = io.BytesIO(data)

    msg_type = reader.read(1)[0]
    if msg_type != MessageType.PROFILE_CONTENT.value:
        raise ValueError(f"Unknown message type: {msg_type}")

    version = reader.read(1)[0]
    if version != 1:
        console.print(f"[warning]Warning:[/warning] Unsupported version {version}, attempting to continue...")

    compressed = reader.read()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as f:
            inner_data = f.read()
    except (OSError, EOFError) as e:
        raise ValueError(f"Gzip decompression error: {e}") from e

    inner_reader = io.BytesIO(inner_data)

    name = read_varbin_string(inner_reader)
    profile_type_int = struct.unpack(">i", inner_reader.read(4))[0]
    try:
        profile_type = ProfileType(profile_type_int)
    except ValueError as e:
        raise ValueError(f"Unknown profile type: {profile_type_int}") from e

    config = read_varbin_string(inner_reader)

    remote_path = ""
    auto_update = False
    auto_update_interval = 0
    last_updated = 0

    if profile_type != ProfileType.LOCAL:
        remote_path = read_varbin_string(inner_reader)

    if profile_type == ProfileType.REMOTE:
        auto_update = bool(struct.unpack("?", inner_reader.read(1))[0])
        auto_update_interval = struct.unpack(">i", inner_reader.read(4))[0]
        last_updated = struct.unpack(">q", inner_reader.read(8))[0]

    return ProfileContent(
        name=name,
        profile_type=profile_type,
        config=config,
        remote_path=remote_path,
        auto_update=auto_update,
        auto_update_interval=auto_update_interval,
        last_updated=last_updated,
    )


@app.command("encode", help="Compile and encode a JSON configuration into a compressed [bold blue]BPF[/bold blue] file.")
def encode_cmd(  # noqa: PLR0913
    config: Annotated[str, typer.Option("--config", help="JSON string or file path.", rich_help_panel="Input / Output")],
    output: Annotated[
        Path | None, typer.Option("--output", help="Path to save the output .bpf file.", rich_help_panel="Input / Output")
    ] = None,
    name: Annotated[
        str | None, typer.Option("--name", help="Profile name (defaults to file name).", rich_help_panel="Profile Settings")
    ] = None,
    profile_type_arg: Annotated[
        ProfileTypeArg, typer.Option("--type", help="Profile classification.", rich_help_panel="Profile Settings")
    ] = ProfileTypeArg.LOCAL,
    remote_path: Annotated[
        str | None,
        typer.Option("--remote-path", help="Sync URL (required for remote/icloud).", rich_help_panel="Remote Settings"),
    ] = None,
    auto_update: Annotated[
        bool, typer.Option("--auto-update", help="Enable automatic background refreshes.", rich_help_panel="Remote Settings")
    ] = False,
    interval: Annotated[
        int, typer.Option("--auto-update-interval", help="Update interval in seconds.", rich_help_panel="Remote Settings")
    ] = 0,
) -> None:
    """
    Compile and encode a JSON profile configuration into a BPF file.

    Parameters
    ----------
    config : str
        The configuration source, accepting either raw inline JSON or a valid file system path.
    output : Path | None, optional
        The target file location to output the .bpf file. If omitted, outputs raw hex to standard out.
    name : str | None, optional
        Descriptive name for the profile. Defaults to the base name of the input file if unspecified.
    profile_type_arg : ProfileTypeArg, optional
        The locality classification (local, remote, icloud). Defaults to ProfileTypeArg.LOCAL.
    remote_path : str | None, optional
        The synchronization URL path required exclusively for remote or icloud profiles.
    auto_update : bool, optional
        Enables client-side automatic refresh cycles. Defaults to False.
    interval : int, optional
        The update re-sync interval in seconds. Defaults to 0.

    Raises
    ------
    typer.Exit
        Exits with status code 1 if remote constraints are violated, or if disk read/write errors occur.
    """
    config_content = config
    config_file_path: Path | None = None

    potential_path = Path(config_content)
    if potential_path.is_file() or str(config_content).endswith(".json"):
        try:
            config_content = potential_path.read_text(encoding="utf-8")
            config_file_path = potential_path
        except (FileNotFoundError, PermissionError, OSError):
            pass

    profile_name = name or (config_file_path.stem if config_file_path else "Unnamed profile")

    if profile_type_arg in (ProfileTypeArg.REMOTE, ProfileTypeArg.ICLOUD) and not remote_path:
        console.print("[bold error]Error:[/bold error] --remote-path parameter is required for remote and icloud profiles")
        raise typer.Exit(code=1)

    actual_profile_type = ProfileType[profile_type_arg.value.upper()]

    profile = ProfileContent(
        name=profile_name,
        profile_type=actual_profile_type,
        config=config_content,
        remote_path=remote_path or "",
        auto_update=auto_update,
        auto_update_interval=interval or 3600,
        last_updated=int(time.time()),
    )

    encoded_data = encode_profile_content(profile)
    json_bytes = len(config_content.encode("utf-8"))
    bpf_bytes = len(encoded_data)

    if output is not None:
        try:
            output.write_bytes(encoded_data)
            console.print(f"[bold success]Success:[/bold success] Encoded profile saved to: [info]{output.resolve()}[/info]")
            console.print(f"Size reduced from [warning]{json_bytes}[/warning] to [success]{bpf_bytes}[/success] bytes")
        except OSError as e:
            console.print(f"[bold error]Write error:[/bold error] {e}")
            raise typer.Exit(code=1) from e
    else:
        print(encoded_data.hex())


@app.command(
    "decode",
    help="Extract and translate a compressed [bold blue]BPF[/bold blue] file back to [bold yellow]JSON[/bold yellow].",
)
def decode_cmd(
    input_file: Annotated[Path, typer.Option("--input", help="Path to the input .bpf file.", rich_help_panel="I/O Options")],
    output: Annotated[
        Path | None, typer.Option("--output", help="Path to save the extracted JSON.", rich_help_panel="I/O Options")
    ] = None,
    show_meta: Annotated[
        bool,
        typer.Option(
            "--show-meta", help="Render a table with internal profile metadata.", rich_help_panel="Display Options"
        ),
    ] = False,
) -> None:
    """
    Translate a compressed BPF file back into standard sing-box JSON.

    Parameters
    ----------
    input_file : Path
        The file system path to the target .bpf file.
    output : Path | None, optional
        The target file system path to save the extracted JSON config. If omitted, outputs to stdout.
    show_meta : bool, optional
        When True, renders a detailed Rich layout table containing metadata variables. Defaults to False.

    Raises
    ------
    typer.Exit
        Exits with status code 1 if file access fails or if binary decoding routines crash.
    """
    if not input_file.exists():
        console.print(f"[bold error]Error:[/bold error] File not found: {input_file}")
        raise typer.Exit(code=1)

    try:
        data = input_file.read_bytes()
    except OSError as e:
        console.print(f"[bold error]Read error:[/bold error] {e}")
        raise typer.Exit(code=1) from e

    try:
        profile = decode_bpf(data)
    except ValueError as e:
        console.print(f"[bold error]Decoding error:[/bold error] {e}")
        raise typer.Exit(code=1) from e

    if show_meta:
        table = Table(title="Profile Metadata", title_style="bold primary")
        table.add_column("Property", justify="right", style="info", no_wrap=True)
        table.add_column("Value", style="secondary")

        table.add_row("Name", profile.name)
        table.add_row("Type", profile.profile_type.name)
        if profile.remote_path:
            table.add_row("Remote path", profile.remote_path)
        table.add_row("Auto-update", str(profile.auto_update))
        if profile.auto_update:
            table.add_row("Interval", f"{profile.auto_update_interval} sec")
        table.add_row("Updated", str(profile.last_updated))

        console.print(table)

    if output is not None:
        try:
            output.write_text(profile.config, encoding="utf-8")
            console.print(f"[bold success]Success:[/bold success] Configuration saved to: [info]{output.resolve()}[/info]")
        except OSError as e:
            console.print(f"[bold error]Write error:[/bold error] {e}")
            raise typer.Exit(code=1) from e
    else:
        print(profile.config)
