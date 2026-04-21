"""
MIDI utility functions for RetroMIDI.
"""

import subprocess
import re


def list_midi_ports():
    """
    Run `aplaymidi -l` and parse the output.
    Returns a list of (port_id, port_name) tuples, e.g. [("20:0", "MidiSport 2x2"), ...]
    """
    try:
        result = subprocess.run(
            ["aplaymidi", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout
    except FileNotFoundError:
        return []
    except Exception:
        return []

    ports = []
    # Typical line format:
    #  20:0    MidiSport 2x2 MIDI 1
    for line in output.splitlines():
        line = line.strip()
        # Skip header lines
        if line.startswith("Port") or not line:
            continue
        # Match port id like "20:0" or "128:0"
        m = re.match(r'^(\d+:\d+)\s+(.+)$', line)
        if m:
            port_id = m.group(1).strip()
            port_name = m.group(2).strip()
            ports.append((port_id, port_name))
    return ports
