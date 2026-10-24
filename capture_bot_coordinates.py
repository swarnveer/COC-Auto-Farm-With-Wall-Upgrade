"""Guided coordinate capture wizard for finalworking_version.py.

Run this while the game is visible. The wizard asks for each region or point
and saves the results to:

    captured_coordinates.json
    captured_coordinates.py

Press ESC during any capture to cancel the wizard.
"""

import json
import os
import tkinter as tk
from pathlib import Path

from pynput import keyboard, mouse


OUTPUT_JSON = Path(__file__).with_name("captured_coordinates.json")
OUTPUT_PY = Path(__file__).with_name("captured_coordinates.py")


class CaptureWizard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Clash of Clans Bot - Coordinate Capture")
        self.root.geometry("560x190+20+20")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.title_var = tk.StringVar(value="Ready")
        self.instruction_var = tk.StringVar(value="Click Start, then follow the prompts.")
        self.status_var = tk.StringVar(value="ESC cancels the current capture.")

        tk.Label(self.root, textvariable=self.title_var, font=("Segoe UI", 13, "bold")).pack(pady=(12, 4))
        tk.Label(
            self.root,
            textvariable=self.instruction_var,
            font=("Segoe UI", 10),
            wraplength=520,
            justify="center",
        ).pack(pady=4)
        tk.Label(self.root, textvariable=self.status_var, fg="#555555").pack(pady=4)

        buttons = tk.Frame(self.root)
        buttons.pack(pady=8)
        self.start_button = tk.Button(buttons, text="Start capture", width=16, command=self.start)
        self.start_button.pack(side="left", padx=5)
        self.pause_button = tk.Button(
            buttons,
            text="Pause capture",
            width=16,
            command=self.toggle_pause,
            state="disabled",
        )
        self.pause_button.pack(side="left", padx=5)
        tk.Button(buttons, text="Exit", width=12, command=self.root.destroy).pack(side="left", padx=5)

        self.running = False
        self.cancelled = False
        self.capture_paused = False
        self.keyboard_listener = keyboard.Listener(on_press=self.on_key)
        self.keyboard_listener.start()

    def on_key(self, key):
        if key == keyboard.Key.esc:
            self.cancelled = True
            return False

    def set_prompt(self, title, instruction):
        self.capture_paused = False
        self.pause_button.config(text="Pause capture")
        self.title_var.set(title)
        self.instruction_var.set(instruction)
        self.status_var.set("Capture active. Use Pause before changing screens.")
        self.root.update_idletasks()

    def toggle_pause(self):
        if not self.running:
            return
        self.capture_paused = not self.capture_paused
        if self.capture_paused:
            self.pause_button.config(text="Resume capture")
            self.status_var.set("PAUSED — navigate to the next screen, then click Resume capture.")
        else:
            self.pause_button.config(text="Pause capture")
            self.status_var.set("Capture active. Your next game-screen action will be recorded.")
        self.root.update_idletasks()

    def _is_wizard_click(self, x, y):
        """Ignore clicks on the wizard so Pause/Resume is never captured."""
        try:
            left = self.root.winfo_rootx()
            top = self.root.winfo_rooty()
            right = left + self.root.winfo_width()
            bottom = top + self.root.winfo_height()
            return left <= x <= right and top <= y <= bottom
        except tk.TclError:
            return True

    def wait_for_point(self):
        result = {}

        def on_click(x, y, button, pressed):
            if self.capture_paused or self._is_wizard_click(x, y):
                return
            if button == mouse.Button.left and not pressed:
                result["point"] = (int(x), int(y))
                return False

        with mouse.Listener(on_click=on_click) as listener:
            while listener.running and not self.cancelled:
                self.root.update()
                self.root.after(20)
        return result.get("point")

    def wait_for_region(self):
        result = {}
        start = {}

        def on_click(x, y, button, pressed):
            if button != mouse.Button.left:
                return
            if self.capture_paused or self._is_wizard_click(x, y):
                return
            if pressed:
                start["point"] = (int(x), int(y))
            elif "point" in start:
                x1, y1 = start["point"]
                x2, y2 = int(x), int(y)
                result["region"] = (
                    min(x1, x2),
                    min(y1, y2),
                    abs(x2 - x1),
                    abs(y2 - y1),
                )
                return False

        with mouse.Listener(on_click=on_click) as listener:
            while listener.running and not self.cancelled:
                self.root.update()
                self.root.after(20)
        return result.get("region")

    def capture_point(self, title, instruction):
        self.set_prompt(title, instruction)
        return self.wait_for_point()

    def capture_region(self, title, instruction):
        self.set_prompt(title, instruction)
        return self.wait_for_region()

    def start(self):
        if self.running:
            return
        if not self.keyboard_listener.running:
            self.keyboard_listener = keyboard.Listener(on_press=self.on_key)
            self.keyboard_listener.start()
        self.running = True
        self.cancelled = False
        self.capture_paused = False
        self.start_button.config(state="disabled")
        self.pause_button.config(state="normal", text="Pause capture")
        # run_capture pumps Tk events while waiting for global mouse input, so
        # it must stay on the Tk thread rather than updating widgets in a
        # worker thread.
        self.root.after(50, self.run_capture)

    def run_capture(self):
        # Region captures
        regions = {}
        regions["attack_gold_region"] = self.capture_region(
            "1/4 - Attack Gold OCR region",
            "On the attack/scouting screen, drag from the top-left to bottom-right of the Gold number only.",
        )
        regions["attack_elixir_region"] = self.capture_region(
            "2/4 - Attack Elixir OCR region",
            "Drag around the Elixir number only on the attack/scouting screen.",
        )
        regions["home_gold_storage_region"] = self.capture_region(
            "3/4 - Home Gold storage region",
            "Return to the village screen, then drag around the Gold storage number only.",
        )
        regions["home_elixir_storage_region"] = self.capture_region(
            "4/4 - Home Elixir storage region",
            "Drag around the Elixir storage number only.",
        )
        if self.cancelled:
            return self.finish_cancelled()

        points = {}
        points["next_base_click"] = self.capture_point(
            "5 - Next base fallback click",
            "Click the Next button once. This is only used if next.png is not found.",
        )
        if self.cancelled:
            return self.finish_cancelled()

        attack_points = self.capture_points(
            "6 - Attack troop path",
            "Click 31 battlefield points in order. These points form the full Troop 1 path.",
            31,
        )
        spell1_points = self.capture_points(
            "7 - Spell 1 points",
            "Click the five Spell 1 drop points in order.",
            5,
        )
        spell2_point = self.capture_point(
            "8 - Spell 2 point",
            "Click the Spell 2 drop location once.",
        )
        single_drop_point = self.capture_point(
            "9 - Troop 3 and hero point",
            "Click one battlefield point. Troop 3 and every hero will use this point.",
        )
        if self.cancelled:
            return self.finish_cancelled()

        data = {
            **regions,
            **points,
            "attack_points": attack_points,
            "spell1_points": spell1_points,
            "spell2_point": spell2_point,
            "single_drop_point": single_drop_point,
        }
        self.save(data)

    def capture_points(self, title, instruction, count):
        values = []
        for index in range(count):
            point = self.capture_point(
                f"{title} ({index + 1}/{count})",
                instruction + " The next click will be recorded now.",
            )
            if point is None:
                self.cancelled = True
                return values
            values.append(point)
        return values

    def save(self, data):
        # Derive the requested attack sequences from the captured path.
        data["troop1_points"] = data["attack_points"] + data["attack_points"][:19]
        data["troop2_points"] = data["attack_points"][:10]

        OUTPUT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")

        py_lines = [
            "# Generated by capture_bot_coordinates.py",
            "# Do not edit manually; rerun the capture wizard instead.",
            "",
        ]
        for key, value in data.items():
            py_lines.append(f"{key.upper()} = {value!r}")
        OUTPUT_PY.write_text("\n".join(py_lines) + "\n", encoding="utf-8")

        self.root.after(0, lambda: self.finish_saved(data))

    def finish_saved(self, data):
        self.title_var.set("Capture complete")
        self.instruction_var.set(
            f"Saved {len(data['attack_points'])} attack points, 5 Spell 1 points, and all OCR regions."
        )
        self.status_var.set(f"Created {OUTPUT_JSON.name} and {OUTPUT_PY.name}")
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled", text="Pause capture")
        self.running = False

    def finish_cancelled(self):
        self.root.after(0, self._show_cancelled)

    def _show_cancelled(self):
        self.title_var.set("Capture cancelled")
        self.instruction_var.set("No files were written. Click Start capture to try again.")
        self.status_var.set("ESC or Exit was used.")
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled", text="Pause capture")
        self.running = False

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    CaptureWizard().run()
