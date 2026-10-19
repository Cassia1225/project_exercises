from pathlib import Path
import streamlit.components.v1 as components

_component = components.declare_component(
    "pollen_browser", path=str(Path(__file__).parent / "browser_component")
)


def browser_bridge(profile, ready, ack):
    return _component(
        profile={
            "version": 1,
            **profile,
        },
        settings_ready=ready,
        ack_event=ack,
        default=None,
        key="browser_bridge",
    )
