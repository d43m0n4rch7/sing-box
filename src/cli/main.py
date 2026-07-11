"""
sing-box Main Entry Point.

Orchestrate the sing-box CLI suite, providing a standard command-line interface
via Typer. Aggregates discrete modules for fetching, generating, and converting.
"""

import typer

from cli.commands import converter_app, fetcher_app, generate_app

app = typer.Typer(
    name="sing-box",
    help="Subscription fetching and conversion, configuration generation",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

app.add_typer(
    fetcher_app,
    name="fetcher",
    help="[bold green]Fetch[/bold green] and manage VLESS subscriptions.",
    rich_help_panel="Network & Subscriptions",
)

app.add_typer(
    generate_app,
    name="generate",
    help="[bold yellow]Generate[/bold yellow] and mutate sing-box JSON configurations.",
    rich_help_panel="Configuration Processing",
)

app.add_typer(
    converter_app,
    name="converter",
    help="[bold blue]Encode & Decode[/bold blue] binary BPF profiles.",
    rich_help_panel="Configuration Processing",
)

if __name__ == "__main__":
    app()
