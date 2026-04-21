# RetroMIDI

A retro-styled GTK3 MIDI player for Linux/GNOME, built around `aplaymidi`.

```
◆ RETROMIDI SEQUENCER ◆
┌────────────────────────────────────┐
│  canyon.mid                        │
│  ▶  PLAYING                        │
│  PORT: 20:0                        │
│  ▁▂▅▇▆▄▂▃▅▇▆▃▁▂▄▆▇▅▃▁▂▄▆          │
└────────────────────────────────────┘
  [⏮] [⏹] [⏵] [⏭] [⏏] [⚙]
```

## Features

- Retro phosphor-green terminal aesthetic
- Directory-based playlist (lists all `.mid` / `.midi` files)
- Play / Stop / Prev / Next transport controls
- Animated VU meter during playback
- Settings dialog with MIDI port selection (parsed from `aplaymidi -l`)
- Config persisted to `~/.config/retromidi/config.json`
- Remembers last directory across sessions

## Requirements

### System packages (install once)

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 alsa-utils
```

### Optional — nicer font

```bash
sudo apt install fonts-share-tech-mono
```

## Installation

### From source (recommended)

```bash
git clone https://github.com/yourname/retromidi.git
cd retromidi
pip install --break-system-packages .
```

### From PyPI (once published)

```bash
pip install --break-system-packages retromidi
```

> **Note:** `PyGObject` (the `gi` module) cannot be installed via pip on most
> distros — it must come from your system package manager as shown above.

## Usage

```bash
retromidi
```

1. Click **⏏ OPEN** to choose a directory of MIDI files.
2. Double-click a track in the playlist to play it immediately.
3. Use transport buttons or let tracks play through automatically.
4. Click **⚙ SETTINGS** to select your MIDI output port.

## Configuration

Settings are stored in `~/.config/retromidi/config.json`:

```json
{
  "port": "20:0",
  "last_dir": "/home/user/personal"
}
```

## MIDI Port

Find your device's port with:

```bash
aplaymidi -l
```

Then set it in **⚙ Settings** or edit the config file directly.

## License

MIT
