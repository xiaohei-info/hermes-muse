"""Hermes discovers this repository as a standalone plugin."""
from pathlib import Path


def register(ctx):
    from .hermes_muse.runtime import register as register_plugin
    register_plugin(ctx, plugin_root=Path(__file__).resolve().parent)
