"""Hermes discovers this repository as a standalone plugin."""
def register(ctx):
    from .hermes_muse.runtime import register as register_plugin
    register_plugin(ctx)
