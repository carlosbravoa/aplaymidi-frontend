"""
RetroMIDI Player - A retro-styled MIDI player for Linux/GNOME
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, Pango

import os
import subprocess
import threading
import time
import json
from pathlib import Path
from .config import Config
from .midi_utils import list_midi_ports


class RetroMIDIPlayer(Gtk.Window):
    def __init__(self):
        super().__init__(title="RetroMIDI")
        self.config = Config()
        self.playlist = []
        self.current_index = -1
        self.process = None
        self.is_playing = False
        self.play_thread = None
        self.shuffle = self.config.get("shuffle", False)
        self.recurse = self.config.get("recurse", False)
        self._shuffle_history = []   # indices already played in shuffle mode

        self._build_ui()
        self._load_css()
        self._restore_last_dir()

        self.connect("destroy", self._on_quit)
        self.set_default_size(620, 500)
        self.set_resizable(False)
        self.show_all()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.set_border_width(0)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.get_style_context().add_class("retro-outer")
        self.add(outer)

        # Title bar strip
        titlebar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        titlebar.get_style_context().add_class("retro-titlebar")
        lbl = Gtk.Label(label="◆ RETROMIDI SEQUENCER ◆")
        lbl.get_style_context().add_class("retro-brand")
        titlebar.pack_start(lbl, True, True, 0)
        outer.pack_start(titlebar, False, False, 0)

        # VU / display area
        display_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        display_box.get_style_context().add_class("retro-display-box")
        outer.pack_start(display_box, False, False, 0)

        self.now_playing_label = Gtk.Label(label="── NO FILE LOADED ──")
        self.now_playing_label.get_style_context().add_class("retro-now-playing")
        self.now_playing_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.now_playing_label.set_max_width_chars(40)
        display_box.pack_start(self.now_playing_label, False, False, 0)

        self.status_label = Gtk.Label(label="STOPPED")
        self.status_label.get_style_context().add_class("retro-status")
        display_box.pack_start(self.status_label, False, False, 0)

        self.port_label = Gtk.Label(label=f"PORT: {self.config.get('port', 'NOT SET')}")
        self.port_label.get_style_context().add_class("retro-port-label")
        display_box.pack_start(self.port_label, False, False, 0)

        # VU meter decoration
        self.vu_bar = Gtk.Label(label=self._vu_idle())
        self.vu_bar.get_style_context().add_class("retro-vu")
        display_box.pack_start(self.vu_bar, False, False, 0)

        # Transport controls
        transport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        transport.get_style_context().add_class("retro-transport")
        outer.pack_start(transport, False, False, 0)

        btn_data = [
            ("⏮", "retro-btn-nav",   self._on_prev,      "PREV"),
            ("⏹", "retro-btn-stop",  self._on_stop,      "STOP"),
            ("⏵", "retro-btn-play",  self._on_play,      "PLAY"),
            ("⏭", "retro-btn-nav",   self._on_next,      "NEXT"),
            ("⏏", "retro-btn-open",  self._on_open_dir,  "OPEN"),
            ("⚙", "retro-btn-cfg",   self._on_settings,  "SETTINGS"),
        ]

        for symbol, css_class, handler, tooltip in btn_data:
            btn = Gtk.Button(label=symbol)
            btn.get_style_context().add_class("retro-btn")
            btn.get_style_context().add_class(css_class)
            btn.set_tooltip_text(tooltip)
            btn.connect("clicked", handler)
            transport.pack_start(btn, True, True, 0)

        # Second row: toggle buttons
        toggles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toggles.get_style_context().add_class("retro-toggles")
        outer.pack_start(toggles, False, False, 0)

        self.shuffle_btn = Gtk.ToggleButton(label="⇀ SHUFFLE")
        self.shuffle_btn.get_style_context().add_class("retro-btn")
        self.shuffle_btn.get_style_context().add_class("retro-btn-toggle")
        self.shuffle_btn.set_tooltip_text("Toggle shuffle playback")
        self.shuffle_btn.set_active(self.shuffle)
        self.shuffle_btn.connect("toggled", self._on_shuffle_toggled)
        toggles.pack_start(self.shuffle_btn, True, True, 0)

        self.recurse_btn = Gtk.ToggleButton(label="⤵ SUBFOLDERS")
        self.recurse_btn.get_style_context().add_class("retro-btn")
        self.recurse_btn.get_style_context().add_class("retro-btn-toggle")
        self.recurse_btn.set_tooltip_text("Include files from subfolders")
        self.recurse_btn.set_active(self.recurse)
        self.recurse_btn.connect("toggled", self._on_recurse_toggled)
        toggles.pack_start(self.recurse_btn, True, True, 0)

        # Playlist
        pl_frame = Gtk.Frame()
        pl_frame.get_style_context().add_class("retro-pl-frame")
        outer.pack_start(pl_frame, True, True, 0)

        pl_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        pl_frame.add(pl_inner)

        pl_header = Gtk.Label(label="▼ PLAYLIST")
        pl_header.get_style_context().add_class("retro-pl-header")
        pl_header.set_xalign(0)
        pl_inner.pack_start(pl_header, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        pl_inner.pack_start(scroll, True, True, 0)

        self.playlist_store = Gtk.ListStore(str, str)  # display name, full path
        self.playlist_view = Gtk.TreeView(model=self.playlist_store)
        self.playlist_view.get_style_context().add_class("retro-playlist")
        self.playlist_view.set_headers_visible(False)
        self.playlist_view.set_activate_on_single_click(False)
        self.playlist_view.connect("row-activated", self._on_row_activated)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        col = Gtk.TreeViewColumn("Track", renderer, text=0)
        self.playlist_view.append_column(col)
        scroll.add(self.playlist_view)

        # Bottom status strip
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bottom.get_style_context().add_class("retro-bottom")
        self.dir_label = Gtk.Label(label="No directory loaded")
        self.dir_label.get_style_context().add_class("retro-dir-label")
        self.dir_label.set_ellipsize(Pango.EllipsizeMode.START)
        self.dir_label.set_xalign(0)
        bottom.pack_start(self.dir_label, True, True, 4)
        outer.pack_start(bottom, False, False, 0)

    # ── CSS ──────────────────────────────────────────────────────────────────

    def _load_css(self):
        css = b"""
        .retro-outer {
            background-color: #1a1a1a;
        }
        .retro-titlebar {
            background-color: #0d0d0d;
            padding: 6px 12px;
            border-bottom: 2px solid #c87c00;
        }
        .retro-brand {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 13px;
            font-weight: bold;
            color: #c87c00;
            letter-spacing: 4px;
        }
        .retro-display-box {
            background-color: #0a1a0a;
            border: 2px solid #2a4a2a;
            border-radius: 4px;
            margin: 10px 12px 6px 12px;
            padding: 10px 14px;
        }
        .retro-now-playing {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 15px;
            color: #00e060;
            letter-spacing: 1px;
        }
        .retro-status {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 11px;
            color: #40a060;
            letter-spacing: 3px;
        }
        .retro-port-label {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 10px;
            color: #2a8040;
            letter-spacing: 2px;
        }
        .retro-vu {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 12px;
            color: #00cc50;
            letter-spacing: 1px;
        }
        .retro-transport {
            background-color: #141414;
            padding: 8px 12px;
            border-top: 1px solid #333;
            border-bottom: 1px solid #333;
        }
        .retro-btn {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 18px;
            background-color: #222;
            border: 2px solid #555;
            border-radius: 3px;
            color: #aaa;
            padding: 6px 4px;
            min-width: 50px;
            transition: all 80ms;
        }
        .retro-btn:hover {
            background-color: #2a2a2a;
            border-color: #888;
        }
        .retro-btn:active {
            background-color: #111;
            border-color: #c87c00;
        }
        .retro-btn-play {
            color: #00e060;
            border-color: #006030;
        }
        .retro-btn-play:hover {
            background-color: #0a2010;
            border-color: #00c050;
        }
        .retro-btn-stop {
            color: #e04020;
            border-color: #601000;
        }
        .retro-btn-stop:hover {
            background-color: #201008;
            border-color: #c03010;
        }
        .retro-btn-nav {
            color: #c87c00;
            border-color: #604000;
        }
        .retro-btn-nav:hover {
            background-color: #201800;
            border-color: #c87c00;
        }
        .retro-btn-open {
            color: #4090e0;
            border-color: #203060;
        }
        .retro-btn-open:hover {
            background-color: #081020;
            border-color: #4090e0;
        }
        .retro-btn-cfg {
            color: #a060e0;
            border-color: #402060;
        }
        .retro-btn-cfg:hover {
            background-color: #100820;
            border-color: #a060e0;
        }
        .retro-pl-frame {
            margin: 6px 12px 0 12px;
            border: 1px solid #2a4a2a;
            border-radius: 2px;
        }
        .retro-pl-header {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 10px;
            color: #406040;
            background-color: #0a1a0a;
            padding: 3px 8px;
            letter-spacing: 3px;
            border-bottom: 1px solid #1a3a1a;
        }
        .retro-playlist {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 12px;
            background-color: #050f05;
            color: #00c050;
        }
        .retro-playlist:selected {
            background-color: #0a3a1a;
            color: #00ff80;
        }
        row:selected {
            background-color: #0a3a1a;
            color: #00ff80;
        }
        .retro-bottom {
            background-color: #0d0d0d;
            padding: 4px 8px;
            border-top: 1px solid #222;
            margin-top: 4px;
        }
        .retro-dir-label {
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            font-size: 10px;
            color: #405040;
        }
        .retro-toggles {
            background-color: #111;
            padding: 5px 12px 7px 12px;
            border-bottom: 1px solid #333;
        }
        .retro-btn-toggle {
            font-size: 11px;
            letter-spacing: 2px;
            color: #506050;
            border-color: #2a3a2a;
            padding: 4px 4px;
        }
        .retro-btn-toggle:checked {
            background-color: #0a2510;
            color: #00ff80;
            border-color: #00c050;
        }
        .retro-btn-toggle:hover {
            border-color: #508050;
            color: #80c080;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── VU meter ─────────────────────────────────────────────────────────────

    def _vu_idle(self):
        return "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁"

    def _vu_playing(self, tick):
        import random
        chars = "▁▂▃▄▅▆▇█"
        bars = []
        for i in range(24):
            h = random.choices(range(len(chars)), weights=[8,6,5,4,3,2,1,1])[0]
            bars.append(chars[h])
        return "".join(bars)

    def _start_vu_animation(self):
        self._vu_tick = 0
        self._vu_timer = GLib.timeout_add(120, self._update_vu)

    def _stop_vu_animation(self):
        if hasattr(self, "_vu_timer") and self._vu_timer:
            GLib.source_remove(self._vu_timer)
            self._vu_timer = None
        self.vu_bar.set_text(self._vu_idle())

    def _update_vu(self):
        if not self.is_playing:
            return False
        self._vu_tick += 1
        self.vu_bar.set_text(self._vu_playing(self._vu_tick))
        return True

    # ── Playlist ─────────────────────────────────────────────────────────────

    def _load_directory(self, path):
        self.playlist_store.clear()
        self.playlist = []
        self._shuffle_history = []
        midi_exts = {".mid", ".midi", ".MID", ".MIDI"}
        root = Path(path)

        if self.recurse:
            files = sorted(
                [f for f in root.rglob("*")
                 if f.is_file() and f.suffix in midi_exts],
                key=lambda f: (str(f.parent).lower(), f.name.lower())
            )
        else:
            files = sorted(
                [f for f in root.iterdir()
                 if f.is_file() and f.suffix in midi_exts],
                key=lambda f: f.name.lower()
            )

        for f in files:
            self.playlist.append(str(f))
            # Show relative path when recursing so subdir is visible
            display = str(f.relative_to(root)) if self.recurse else f.name
            self.playlist_store.append([display, str(f)])

        self.current_index = 0 if self.playlist else -1
        self.config.set("last_dir", str(path))
        self.config.save()
        self.dir_label.set_text(str(path))

        if self.playlist:
            self._select_row(0)

    def _select_row(self, index):
        if 0 <= index < len(self.playlist):
            path = Gtk.TreePath.new_from_indices([index])
            self.playlist_view.get_selection().select_path(path)
            self.playlist_view.scroll_to_cell(path, None, True, 0.5, 0)
            fname = Path(self.playlist[index]).name
            self.now_playing_label.set_text(fname)

    def _restore_last_dir(self):
        last = self.config.get("last_dir")
        if last and os.path.isdir(last):
            self._load_directory(last)

    # ── Playback ─────────────────────────────────────────────────────────────

    def _play_current(self):
        if self.current_index < 0 or self.current_index >= len(self.playlist):
            return
        self._stop_process()

        port = self.config.get("port", "20:0")
        midi_file = self.playlist[self.current_index]
        self._select_row(self.current_index)

        self.is_playing = True
        self.status_label.set_text("▶  PLAYING")
        self._start_vu_animation()

        def run():
            try:
                self.process = subprocess.Popen(
                    ["aplaymidi", "--port", port, midi_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.process.wait()
            except FileNotFoundError:
                GLib.idle_add(self._show_error,
                              "aplaymidi not found.\nInstall with: sudo apt install alsa-utils")
                return
            finally:
                if self.is_playing:
                    GLib.idle_add(self._auto_next)

        self.play_thread = threading.Thread(target=run, daemon=True)
        self.play_thread.start()

    def _auto_next(self):
        if not self.is_playing:
            return
        if self.shuffle:
            self._play_shuffle_next()
        elif self.current_index + 1 < len(self.playlist):
            self.current_index += 1
            self._play_current()
        else:
            self._set_stopped()

    def _play_shuffle_next(self):
        import random
        remaining = [i for i in range(len(self.playlist))
                     if i not in self._shuffle_history]
        if not remaining:
            # Full cycle done — restart
            self._shuffle_history = []
            remaining = list(range(len(self.playlist)))
        self.current_index = random.choice(remaining)
        self._shuffle_history.append(self.current_index)
        self._play_current()

    def _stop_process(self):
        self.is_playing = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self._midi_reset()

    def _midi_reset(self):
        """Send all_notes_off.mid to silence stuck notes on every channel."""
        reset_file = self.config.get("reset_midi", "")
        if not reset_file:
            # Auto-discover: look next to current song, then in config dir
            from .config import CONFIG_DIR
            candidates = []
            if self.playlist and 0 <= self.current_index < len(self.playlist):
                song_dir = Path(self.playlist[self.current_index]).parent
                candidates.append(song_dir / "all_notes_off.mid")
            candidates.append(CONFIG_DIR / "all_notes_off.mid")
            for c in candidates:
                if c.exists():
                    reset_file = str(c)
                    break

        if not reset_file:
            return

        port = self.config.get("port", "20:0")
        try:
            subprocess.run(
                ["aplaymidi", "--port", port, reset_file],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass  # Never block UI for reset failures

    def _set_stopped(self):
        self.is_playing = False
        self.status_label.set_text("■  STOPPED")
        self._stop_vu_animation()

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _on_shuffle_toggled(self, btn):
        self.shuffle = btn.get_active()
        self._shuffle_history = []
        self.config.set("shuffle", self.shuffle)
        self.config.save()

    def _on_recurse_toggled(self, btn):
        self.recurse = btn.get_active()
        self.config.set("recurse", self.recurse)
        self.config.save()
        # Reload current directory with new setting
        last = self.config.get("last_dir")
        if last and os.path.isdir(last):
            was_playing = self.is_playing
            self._stop_process()
            self._set_stopped()
            self._load_directory(last)

    def _on_play(self, btn):
        if self.is_playing:
            # Pause = stop process but keep position
            self._stop_process()
            self._set_stopped()
        else:
            if self.current_index < 0 and self.playlist:
                self.current_index = 0
            self._play_current()

    def _on_stop(self, btn):
        self._stop_process()
        self._set_stopped()

    def _on_prev(self, btn):
        if not self.playlist:
            return
        was_playing = self.is_playing
        self._stop_process()
        self.current_index = max(0, self.current_index - 1)
        if was_playing:
            self._play_current()
        else:
            self._select_row(self.current_index)
            self.now_playing_label.set_text(
                Path(self.playlist[self.current_index]).name)
            self._set_stopped()

    def _on_next(self, btn):
        if not self.playlist:
            return
        was_playing = self.is_playing
        self._stop_process()
        self.current_index = min(len(self.playlist) - 1, self.current_index + 1)
        if was_playing:
            self._play_current()
        else:
            self._select_row(self.current_index)
            self.now_playing_label.set_text(
                Path(self.playlist[self.current_index]).name)
            self._set_stopped()

    def _on_open_dir(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Open MIDI Directory",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,   Gtk.ResponseType.OK,
        )
        last = self.config.get("last_dir")
        if last and os.path.isdir(last):
            dialog.set_current_folder(last)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self._stop_process()
            self._set_stopped()
            self._load_directory(dialog.get_filename())
        dialog.destroy()

    def _on_row_activated(self, view, path, column):
        index = path.get_indices()[0]
        self.current_index = index
        self._stop_process()
        self._play_current()

    def _on_settings(self, btn):
        SettingsDialog(self).run_dialog()

    def _on_quit(self, *args):
        self._stop_process()
        Gtk.main_quit()

    def _show_error(self, msg):
        d = Gtk.MessageDialog(parent=self, flags=0,
                              message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.OK, text=msg)
        d.run()
        d.destroy()

    def refresh_port_label(self):
        self.port_label.set_text(f"PORT: {self.config.get('port', 'NOT SET')}")


# ── Settings Dialog ───────────────────────────────────────────────────────────

class SettingsDialog:
    def __init__(self, parent):
        self.parent = parent
        self.config = parent.config

    def run_dialog(self):
        dialog = Gtk.Dialog(title="Settings", parent=self.parent,
                            flags=Gtk.DialogFlags.MODAL)
        dialog.set_default_size(480, 320)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(16)

        # Port selection
        ports = list_midi_ports()
        port_label = Gtk.Label(label="MIDI Output Port:")
        port_label.set_xalign(0)
        port_label.get_style_context().add_class("retro-status")
        box.pack_start(port_label, False, False, 0)

        port_combo = Gtk.ComboBoxText()
        current_port = self.config.get("port", "")
        selected_i = 0
        for i, (port_id, port_name) in enumerate(ports):
            port_combo.append_text(f"{port_id}  —  {port_name}")
            if port_id == current_port:
                selected_i = i
        if ports:
            port_combo.set_active(selected_i)
        else:
            port_combo.append_text("No ports found — is ALSA running?")
            port_combo.set_active(0)
        box.pack_start(port_combo, False, False, 0)

        # Manual port entry
        manual_label = Gtk.Label(label="Or enter port manually (e.g. 20:0):")
        manual_label.set_xalign(0)
        box.pack_start(manual_label, False, False, 0)

        manual_entry = Gtk.Entry()
        manual_entry.set_text(self.config.get("port", ""))
        manual_entry.set_placeholder_text("e.g. 20:0 or 128:0")
        box.pack_start(manual_entry, False, False, 0)

        # Reset MIDI file
        reset_label = Gtk.Label(label="MIDI Reset file (all_notes_off.mid):")
        reset_label.set_xalign(0)
        box.pack_start(reset_label, False, False, 0)

        reset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        reset_entry = Gtk.Entry()
        reset_entry.set_text(self.config.get("reset_midi", ""))
        reset_entry.set_placeholder_text("Auto-detect: next to songs or ~/.config/retromidi/")
        reset_entry.set_hexpand(True)
        reset_box.pack_start(reset_entry, True, True, 0)
        browse_btn = Gtk.Button(label="Browse…")

        def _browse_reset(b):
            d = Gtk.FileChooserDialog(
                title="Select all_notes_off.mid",
                parent=dialog,
                action=Gtk.FileChooserAction.OPEN,
            )
            d.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                          Gtk.STOCK_OPEN,   Gtk.ResponseType.OK)
            ff = Gtk.FileFilter()
            ff.set_name("MIDI files")
            ff.add_pattern("*.mid")
            ff.add_pattern("*.midi")
            d.add_filter(ff)
            if d.run() == Gtk.ResponseType.OK:
                reset_entry.set_text(d.get_filename())
            d.destroy()

        browse_btn.connect("clicked", _browse_reset)
        reset_box.pack_start(browse_btn, False, False, 0)
        box.pack_start(reset_box, False, False, 0)

        # Raw aplaymidi -l output
        raw_label = Gtk.Label(label="Available ports (aplaymidi -l):")
        raw_label.set_xalign(0)
        box.pack_start(raw_label, False, False, 0)

        raw_view = Gtk.TextView()
        raw_view.set_editable(False)
        raw_view.set_monospace(True)
        raw_view.set_cursor_visible(False)
        raw_buf = raw_view.get_buffer()
        raw_buf.set_text(self._get_raw_ports())
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(80)
        scroll.add(raw_view)
        box.pack_start(scroll, True, True, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            manual = manual_entry.get_text().strip()
            if manual:
                chosen_port = manual
            elif ports:
                idx = port_combo.get_active()
                chosen_port = ports[idx][0] if 0 <= idx < len(ports) else ""
            else:
                chosen_port = ""
            self.config.set("port", chosen_port)
            self.config.set("reset_midi", reset_entry.get_text().strip())
            self.config.save()
            self.parent.refresh_port_label()

        dialog.destroy()

    def _get_raw_ports(self):
        try:
            result = subprocess.run(
                ["aplaymidi", "-l"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout or result.stderr or "No output"
        except FileNotFoundError:
            return "aplaymidi not found. Install alsa-utils."
        except Exception as e:
            return str(e)


def main():
    app = RetroMIDIPlayer()
    Gtk.main()


if __name__ == "__main__":
    main()
