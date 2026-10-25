import pyautogui
import pytesseract
import time
import os
import re
import json
import cv2
import numpy as np
import tkinter as tk
import threading
from collections import Counter
from statistics import median
from pynput import keyboard
from pynput import mouse
from datetime import datetime

# --- CONFIGURATION ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Template folders: all templates are resolved relative to this standalone file.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_WALL_DIR = os.path.join(_SCRIPT_DIR, "debug_wall")
DEBUG_RECOVERY_DIR = os.path.join(_SCRIPT_DIR, "debug_recovery")
os.makedirs(DEBUG_WALL_DIR, exist_ok=True)
os.makedirs(DEBUG_RECOVERY_DIR, exist_ok=True)
_ITEM_CANDIDATES = (
    os.path.join(_SCRIPT_DIR, "item"),
)
_WALL_CANDIDATES = (
    os.path.join(_SCRIPT_DIR, "item", "wall"),
    os.path.join(_SCRIPT_DIR, "walls"),
)


def _first_existing_dir(candidates):
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[-1]


ITEM_DIR = _first_existing_dir(_ITEM_CANDIDATES)
WALL_DIR = _first_existing_dir(_WALL_CANDIDATES)

_warned_missing_templates = set()

# --- COORDINATES & REGIONS ---
GOLD_REGION = (-2365, -78, 268, 57)
ELIXIR_REGION = (-2360, -20, 239, 51)
NEXT_BASE_CLICK = (1588, 842)

# Home Screen Storage
GOLD_STORAGE_REGION = (-494, -181, 428, 59)
ELIXIR_STORAGE_REGION = (-496, -105, 427, 65)

# Row Upgrade Controls
SELECT_ROW_BTN = (968, 735)
PLUS_BTN = (968, 735)
MINUS_BTN = (607, 736)
GOLD_SELECT_CLICK = (1108, 735)
ELIXIR_SELECT_CLICK = (1308, 738)
FINAL_UPGRADE_CONFIRM = (1137, 618)
CLOSE_BTN = (1560, 116)

# --- THE COST BOXES ---
GOLD_COST_REGION = (1059, 664, 129, 39)
ELIXIR_COST_REGION = (1237, 666, 124, 38)
# Exact wall cost-number regions on the current screen. Red means
# unaffordable; white means affordable.
WALL_GOLD_COST_COLOR_REGION = (1422, 1045, 136, 40)
WALL_ELIXIR_COST_COLOR_REGION = (1618, 1044, 131, 40)

# Logic Constants
LOOT_THRESHOLD = 1500000
# Available loot per resource on the scout screen cannot exceed this (game cap).
MAX_LOOT_PER_RESOURCE = 30_000_000
MIN_RESOURCES_TO_KEEP = 600000
WALL_DUMP_THRESHOLD = 17_000_000
MAX_WALLS_PER_GROUP = 4
CHECK_STORAGE_AFTER_EVERY_ATTACK = False
attack_count = 0
start_requested = False

# --- DEPLOY COORDINATES (after selecting each template on bar) ---
ATTACK_POINTS = [
    (-2031, 1000), (-2180, 435), (-2101, 397), (-2052, 359),
    (-1984, 309), (-1944, 267), (-1892, 225), (-1830, 203),
    (-1780, 157), (-1696, 100), (-1654, 70), (-1623, 34),
    (-1566, 5), (-1526, -25), (-1464, -66), (-1427, -94),
    (-1057, -135), (-992, -95), (-970, -65), (-909, -12),
    (-876, 4), (-833, 37), (-791, 61), (-752, 90),
    (-718, 129), (-669, 153), (-636, 193), (-585, 227),
    (-540, 260), (-493, 297), (-412, 336),
]
TROOP_1_COORDS = ATTACK_POINTS + ATTACK_POINTS[:19]
TROOP_2_COORDS = ATTACK_POINTS[:10]
SPELL_1_COORDS = [(-1622, 398), (-1297, 168), (-1340, 601), (-1032, 349), (-1304, 394)]
SPELL_2_DROP = (-1010, 686)
SINGLE_DROP = ATTACK_POINTS[0]
HERO_DEPLOY_COORDS = [SINGLE_DROP, SINGLE_DROP, SINGLE_DROP, SINGLE_DROP]


def _load_captured_coordinates():
    path = os.path.join(_SCRIPT_DIR, "captured_coordinates.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            captured = json.load(handle)

        global GOLD_REGION, ELIXIR_REGION
        global GOLD_STORAGE_REGION, ELIXIR_STORAGE_REGION
        global NEXT_BASE_CLICK
        global ATTACK_POINTS, TROOP_1_COORDS, TROOP_2_COORDS
        global SPELL_1_COORDS, SPELL_2_DROP, SINGLE_DROP, HERO_DEPLOY_COORDS

        GOLD_REGION = tuple(captured["attack_gold_region"])
        ELIXIR_REGION = tuple(captured["attack_elixir_region"])
        GOLD_STORAGE_REGION = tuple(captured["home_gold_storage_region"])
        ELIXIR_STORAGE_REGION = tuple(captured["home_elixir_storage_region"])
        NEXT_BASE_CLICK = tuple(captured["next_base_click"])
        ATTACK_POINTS = [tuple(point) for point in captured["attack_points"]]
        TROOP_1_COORDS = [tuple(point) for point in captured["troop1_points"]]
        TROOP_2_COORDS = [tuple(point) for point in captured["troop2_points"]]
        SPELL_1_COORDS = [tuple(point) for point in captured["spell1_points"]]
        SPELL_2_DROP = tuple(captured["spell2_point"])
        SINGLE_DROP = tuple(captured["single_drop_point"])
        HERO_DEPLOY_COORDS = [tuple(point) for point in captured.get("hero_points", [SINGLE_DROP] * 4)]
        print(f"[INFO] Loaded captured coordinates from {path}")
    except Exception as exc:
        print(f"[WARN] Could not load captured_coordinates.json: {exc}")


_load_captured_coordinates()

# --- TIMING (seconds) — tune for your attack length / machine ---
ATTACK_WAIT_BEFORE_RETURN_HOME = 45.0
LAUNCH_TEMPLATE_TIMEOUT = 45.0
DEPLOY_TEMPLATE_TIMEOUT = 2.0
HERO_DEPLOY_TEMPLATE_TIMEOUT = 1.0
TROOP_DEPLOY_CLICK_DELAY = 0.03
RETURN_HOME_POLL_INTERVAL = 1.0
RETURN_HOME_STABLE_HITS = 2
HOME_CONFIRM_TIMEOUT = 20.0
HOME_CONFIRM_STABLE_HITS = 2
POST_RETURN_HOME_WAIT = 3.2
CLEANUP_MATCH_CONFIDENCES = (0.90, 0.84, 0.78)
CLOUD_SEARCH_POLL = 1.0
LAUNCH_PAUSE_1 = 2.6
LAUNCH_PAUSE_2 = 0.95
LAUNCH_PAUSE_3 = 1.25
MAINTENANCE_UI_WAIT = 1.4
POST_DUMP_VERIFY_WAIT = 1.2
LOOT_OCR_SETTLE = 0.28
NEXT_BASE_WAIT = 1.15
OCR_SAMPLES_LOOT = 1
OCR_SAMPLES_STORAGE = 2

# --- GUI ---
_LOG_COLOR_TAGS = {
    "yellow": "#ffd700",
    "green": "#6eeb83",
    "red": "#ff6b6b",
    "orange": "#ffa94d",
    "cyan": "#40e0d0",
    "white": "#f0f0f0",
    "purple": "#da70d6",
    "pink": "#ffb6c1",
}


class StatusOverlay:
    """Top panel: header, current phase, latest finding, rolling log."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes("-topmost", True, "-alpha", 0.94)
        self.root.overrideredirect(True)
        w, h = 580, 320
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        self.root.geometry(f"{w}x{h}+{x}+4")
        self.root.configure(bg="#141414")

        self.phase_var = tk.StringVar(value="READY — Press PAGE UP to arm the bot")
        self.finding_var = tk.StringVar(value="")

        self._header = tk.Label(
            self.root,
            text="",
            font=("Consolas", 10, "bold"),
            fg="#9ae6b4",
            bg="#141414",
            anchor="w",
        )
        self._header.pack(fill="x", padx=8, pady=(6, 2))

        tk.Label(self.root, text="Step / phase", font=("Segoe UI", 8), fg="#718096", bg="#141414", anchor="w").pack(
            fill="x", padx=8
        )
        self._phase = tk.Label(
            self.root,
            textvariable=self.phase_var,
            font=("Consolas", 11, "bold"),
            fg="#f6e05e",
            bg="#141414",
            anchor="w",
            justify="left",
            wraplength=w - 16,
        )
        self._phase.pack(fill="x", padx=8)

        tk.Label(self.root, text="Latest finding", font=("Segoe UI", 8), fg="#718096", bg="#141414", anchor="w").pack(
            fill="x", padx=8, pady=(6, 0)
        )
        self._finding = tk.Label(
            self.root,
            textvariable=self.finding_var,
            font=("Consolas", 9),
            fg="#90cdf4",
            bg="#141414",
            anchor="w",
            justify="left",
            wraplength=w - 16,
        )
        self._finding.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(self.root, text="Activity log", font=("Segoe UI", 8), fg="#718096", bg="#141414", anchor="w").pack(
            fill="x", padx=8
        )
        self._txt = tk.Text(
            self.root,
            height=10,
            width=78,
            font=("Consolas", 8),
            bg="#0b0b0b",
            fg="#d0d0d0",
            relief="flat",
            state="disabled",
            highlightthickness=0,
            padx=6,
            pady=4,
        )
        self._txt.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        controls = tk.Frame(self.root, bg="#141414")
        controls.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(
            controls,
            text="Edit click sequences",
            command=open_calibration_menu,
            bg="#2d3748",
            fg="white",
            activebackground="#4a5568",
            activeforeground="white",
            relief="flat",
            padx=10,
        ).pack(side="left")
        tk.Label(
            controls,
            text="F12",
            fg="#a0aec0",
            bg="#141414",
            font=("Consolas", 9),
        ).pack(side="left", padx=8)

        self._txt.tag_configure("dim", foreground="#5a5a5a")
        for name, hx in _LOG_COLOR_TAGS.items():
            self._txt.tag_configure(name, foreground=hx)

    def hide(self):
        """Hide the panel so it does not cover the game during an attack."""
        self.root.withdraw()
        self.root.update_idletasks()

    def show(self):
        """Show the panel again after an attack."""
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.update_idletasks()

    def refresh_header(self):
        ts = datetime.now().strftime("%H:%M:%S")
        self._header.config(text=f"  CoC bot  ·  Wins: {attack_count}  ·  {ts}")
        self.root.update_idletasks()

    def set_phase(self, text):
        self.phase_var.set(text)

    def set_finding(self, text):
        self.finding_var.set(text)

    def log_line(self, msg, color="yellow"):
        tag = color if color in _LOG_COLOR_TAGS else "yellow"
        ts = datetime.now().strftime("%H:%M:%S")
        self._txt.configure(state="normal")
        self._txt.insert("end", f"[{ts}] ", "dim")
        self._txt.insert("end", f"{msg}\n", tag)
        line = int(self._txt.index("end-1c").split(".")[0])
        if line > 18:
            self._txt.delete("1.0", f"{line - 16}.0")
        self._txt.see("end")
        self._txt.configure(state="disabled")
        self.root.update_idletasks()


overlay = None
calibration_window = None
calibration_busy = False
calibration_message = None


def status(msg, color="yellow", phase=None, finding=None):
    """Update overlay: optional phase + finding lines, always append to log."""
    ts = datetime.now().strftime("%H:%M:%S")
    if overlay:
        overlay.refresh_header()
        if phase is not None:
            overlay.set_phase(phase)
        if finding is not None:
            overlay.set_finding(finding)
        overlay.log_line(msg, color)
    print(f"[{ts}] {msg}")


def _save_calibration_data():
    data = {}
    path = os.path.join(_SCRIPT_DIR, "captured_coordinates.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data.update(json.load(handle))
    except Exception:
        pass
    data.update({
        "attack_points": [list(p) for p in ATTACK_POINTS],
        "troop1_points": [list(p) for p in TROOP_1_COORDS],
        "troop2_points": [list(p) for p in TROOP_2_COORDS],
        "spell1_points": [list(p) for p in SPELL_1_COORDS],
        "spell2_point": list(SPELL_2_DROP),
        "single_drop_point": list(SINGLE_DROP),
        "hero_points": [list(p) for p in HERO_DEPLOY_COORDS],
    })
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    status(f"CALIBRATION SAVED: {path}", "green", phase="CALIBRATION")


def _calibration_clicks(label, count, callback):
    """Capture count game clicks while the calibration window is minimized."""
    global calibration_busy
    calibration_busy = True
    if calibration_window:
        calibration_window.withdraw()

    points = []
    status(
        f"CALIBRATION: click {count} point(s) for {label}",
        "cyan",
        phase="CALIBRATION",
        finding="The calibration menu is hidden; game clicks only are recorded",
    )

    def on_click(x, y, button, pressed):
        if button == mouse.Button.left and not pressed:
            points.append((int(x), int(y)))
            if len(points) >= count:
                return False

    with mouse.Listener(on_click=on_click) as listener:
        listener.join()

    def finish():
        global calibration_busy
        callback(points)
        calibration_busy = False
        if calibration_window:
            calibration_window.deiconify()
            calibration_window.lift()

    if overlay:
        overlay.root.after(0, finish)


def _start_calibration(label, count, callback):
    if calibration_busy:
        return
    if start_requested:
        status("CALIBRATION BLOCKED: stop/restart bot before recapturing", "red", phase="CALIBRATION")
        return
    status(
        f"CALIBRATION READY: {label}",
        "yellow",
        phase="CALIBRATION",
        finding="Move to the correct screen, then click the game points",
    )
    threading.Thread(
        target=_calibration_clicks,
        args=(label, count, callback),
        daemon=True,
    ).start()


def open_calibration_menu():
    global calibration_window
    if calibration_window and calibration_window.winfo_exists():
        calibration_window.deiconify()
        calibration_window.lift()
        return
    calibration_window = tk.Toplevel(overlay.root)
    calibration_window.title("Bot calibration")
    calibration_window.attributes("-topmost", True)
    calibration_window.geometry("440x430+30+30")
    tk.Label(
        calibration_window,
        text="Calibration menu (F12)",
        font=("Segoe UI", 13, "bold"),
    ).pack(pady=8)
    tk.Label(
        calibration_window,
        text="Use only while the bot is stopped. Click a button, move to the game screen, then click the requested points.",
        wraplength=400,
        justify="center",
    ).pack(pady=4)

    def sequence(label, count, setter):
        def done(points):
            setter(points)
            _save_calibration_data()
        _start_calibration(label, count, done)

    # Each capture count is editable. Troop 1 defaults to 50 and will record
    # exactly that many clicks every time its button is pressed.
    rows = [
        ("Troop 1", 50, _set_troop1),
        ("Troop 2", 10, _set_troop2),
        ("Spell 1", 5, _set_spell1),
        ("Troop 3", 1, _set_single),
        ("Hero 1", 1, lambda p: _set_hero(0, p)),
        ("Hero 2", 1, lambda p: _set_hero(1, p)),
        ("Hero 3", 1, lambda p: _set_hero(2, p)),
        ("Hero 4", 1, lambda p: _set_hero(3, p)),
        ("Spell 2", 1, _set_spell2),
    ]
    for label, default_count, setter in rows:
        row = tk.Frame(calibration_window)
        row.pack(fill="x", padx=18, pady=2)
        tk.Label(row, text=label, width=12, anchor="w").pack(side="left")
        count_entry = tk.Entry(row, width=6, justify="center")
        count_entry.insert(0, str(default_count))
        count_entry.pack(side="left", padx=6)

        def start_row(label=label, setter=setter, entry=count_entry):
            try:
                count = int(entry.get())
                if count < 1 or count > 500:
                    raise ValueError
            except ValueError:
                status(f"CALIBRATION ERROR: {label} count must be 1–500", "red", phase="CALIBRATION")
                return
            sequence(f"{label} — {count} clicks", count, setter)

        tk.Button(row, text="Capture", width=12, command=start_row).pack(side="left")


def _set_troop1(points):
    global TROOP_1_COORDS, ATTACK_POINTS
    TROOP_1_COORDS = list(points)
    ATTACK_POINTS = list(points[:31])


def _set_troop2(points):
    global TROOP_2_COORDS
    TROOP_2_COORDS = list(points)


def _set_spell1(points):
    global SPELL_1_COORDS
    SPELL_1_COORDS = list(points)


def _set_spell2(points):
    global SPELL_2_DROP
    SPELL_2_DROP = points[0]


def _set_single(points):
    global SINGLE_DROP, HERO_DEPLOY_COORDS
    SINGLE_DROP = points[0]
    HERO_DEPLOY_COORDS = [SINGLE_DROP] * 4


def _set_hero(index, points):
    global HERO_DEPLOY_COORDS
    HERO_DEPLOY_COORDS[index] = points[0]

# --- VISION UTILITIES ---

def find_item(item_name, confidence=0.8, region=None, grayscale=True):
    """
    Locate item/<name>.png on screen. Uses grayscale matching when supported
    (more tolerant of small color / gamma differences).
    """
    path = os.path.join(ITEM_DIR, f"{item_name}.png")
    if not os.path.exists(path):
        if item_name not in _warned_missing_templates:
            _warned_missing_templates.add(item_name)
            print(f"[WARN] Missing template file: {path}")
        return None
    try:
        try:
            return pyautogui.locateOnScreen(
                path, confidence=confidence, region=region, grayscale=grayscale
            )
        except TypeError:
            return pyautogui.locateOnScreen(path, confidence=confidence, region=region)
    except Exception:
        return None


def find_click_template_until(
    name,
    *,
    timeout_s=35.0,
    confidence=0.75,
    poll=0.35,
    grayscale=False,
):
    """
    Poll until item/<name>.png is found, then click its center.
    Returns True if clicked, False on timeout.
    """
    path = os.path.join(ITEM_DIR, f"{name}.png")
    if not os.path.exists(path):
        status(
            f"MISSING TEMPLATE: {name}.png",
            "red",
            phase="ATTACK",
            finding=f"Expected: {path}",
        )
        return False
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        loc = None
        for match_confidence in (confidence, 0.65, 0.55):
            loc = find_item(name, confidence=match_confidence, grayscale=grayscale)
            if loc:
                break
        if loc:
            cx, cy = pyautogui.center(loc)
            status(
                f"ATTACK BAR CLICK: {name}.png at ({int(cx)}, {int(cy)}) — deployment armed",
                "cyan",
                phase="ATTACK",
                finding=f"Matched with confidence {match_confidence:.2f}",
            )
            pyautogui.click(cx, cy)
            time.sleep(0.45)
            return True
        time.sleep(poll)
    status(
        f"TIMEOUT: never saw {name}.png",
        "red",
        phase="ATTACK",
        finding=f"Waited {timeout_s:.0f}s",
    )
    return False


def click_deploy_line(coords, delay=None):
    """Click a list of battlefield coordinates quickly."""
    d = TROOP_DEPLOY_CLICK_DELAY if delay is None else delay
    old_pause = pyautogui.PAUSE
    pyautogui.PAUSE = 0.01
    try:
        for index, xy in enumerate(coords, start=1):
            # Keep the watchdog active without doing expensive image scans on
            # every click. The game attack bar is stable during deployment.
            pyautogui.click(xy[0], xy[1])
            time.sleep(d)
    finally:
        pyautogui.PAUSE = old_pause


def launch_attack_from_home():
    """
    Home screen → clouds: click attack1.png, attack2.png, attack3.png in order.
    """
    for index, key in enumerate(("attack1", "attack2", "attack3"), start=1):
        status(
            f"LAUNCH: {key}.png",
            "white",
            phase="LAUNCH",
            finding="Sequential template clicks to start search",
        )
        path = os.path.join(ITEM_DIR, f"{key}.png")
        loc = None
        matched_confidence = None
        for confidence in (0.82, 0.74, 0.66, 0.58):
            try:
                loc = pyautogui.locateOnScreen(path, confidence=confidence, grayscale=True)
                if loc:
                    matched_confidence = confidence
                    break
            except Exception:
                pass
        if not loc:
            status(
                f"LAUNCH FAILED: could not find {key}.png",
                "red",
                phase="LAUNCH",
                finding=f"Search step {index}/3 timed out",
            )
            return False

        point = pyautogui.center(loc)
        status(
            f"LAUNCH CLICK: {key}.png at ({int(point.x)}, {int(point.y)})",
            "cyan",
            phase="LAUNCH",
            finding=f"Matched at confidence {matched_confidence:.2f}",
        )
        pyautogui.moveTo(point.x, point.y, duration=0.15)
        pyautogui.mouseDown()
        time.sleep(0.12)
        pyautogui.mouseUp()

        # Give each transition time to finish. Attack3 needs the longest pause
        # because it opens the attack/cloud screen.
        time.sleep(1.2 if key != "attack3" else 4.0)
    return True


def _parse_int_from_ocr_text(text):
    """Extract integer from OCR; handles spaces, commas, and stray symbols."""
    if not text:
        return None
    s = re.sub(r"[^\d]", "", text)
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _tesseract_read_digits(binary_bgr_or_gray, psm=7):
    """
    Tesseract on a black-on-white (or dark-on-light) image.
    psm 7: single text line; psm 8: single word — both work for compact numbers.
    """
    if len(binary_bgr_or_gray.shape) == 3:
        gray = cv2.cvtColor(binary_bgr_or_gray, cv2.COLOR_BGR2GRAY)
    else:
        gray = np.asarray(binary_bgr_or_gray)
    # Ensure light background for Tesseract
    if np.mean(gray) < 128:
        gray = cv2.bitwise_not(gray)
    padded = cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    uniq = len(np.unique(padded))
    if uniq > 12:
        padded = cv2.bilateralFilter(padded, 5, 50, 50)
        _, sharp = cv2.threshold(padded, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        sharp = padded
    config = r'--oem 3 --psm %d -c tessedit_char_whitelist=0123456789' % psm
    text = pytesseract.image_to_string(sharp, config=config)
    return _parse_int_from_ocr_text(text)


def _tesseract_read_digits_data(binary_gray):
    """Use word-level confidence from image_to_data when string parse is ambiguous."""
    if np.mean(binary_gray) < 128:
        binary_gray = cv2.bitwise_not(binary_gray)
    padded = cv2.copyMakeBorder(binary_gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
    data = pytesseract.image_to_data(
        padded, config=config, output_type=pytesseract.Output.DICT
    )
    chunks = []
    n = len(data["text"])
    for i in range(n):
        try:
            conf = int(data["conf"][i])
        except (ValueError, TypeError):
            continue
        if conf < 40:
            continue
        t = data["text"][i].strip()
        if not t:
            continue
        parsed = _parse_int_from_ocr_text(t)
        if parsed is not None:
            chunks.append(parsed)
    if not chunks:
        return None
    return max(chunks) if chunks else None


def _variants_for_ocr(img_bgr, storage_mode):
    """
    Build several binarized views of the same ROI. CoC text is white/yellow on
    dark UI; outlines break naive thresholds — multiple strategies reduce misses.
    """
    h, w = img_bgr.shape[:2]
    if w < 40 or h < 12:
        scale = 4
    else:
        scale = 3
    big = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    variants = []

    # --- A: HSV bright text mask ---
    hsv = cv2.cvtColor(big, cv2.COLOR_BGR2HSV)
    if storage_mode:
        lower = np.array([0, 0, 195])
        upper = np.array([180, 55, 255])
    else:
        # Slightly wider: loot bar can be warm-white / pale yellow
        lower = np.array([0, 0, 200])
        upper = np.array([180, 80, 255])
    mask_a = cv2.inRange(hsv, lower, upper)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask_a = cv2.morphologyEx(mask_a, cv2.MORPH_OPEN, k)
    mask_a = cv2.morphologyEx(mask_a, cv2.MORPH_CLOSE, k)
    variants.append(cv2.bitwise_not(mask_a))

    # --- B: Grayscale + CLAHE + Otsu (strong default for UI text) ---
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray_e = clahe.apply(gray)
    _, otsu = cv2.threshold(gray_e, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Prefer dark glyphs on white
    if np.mean(otsu) > 127:
        otsu = cv2.bitwise_not(otsu)
    variants.append(otsu)

    # --- C: Adaptive threshold on CLAHE (handles uneven lighting on the bar) ---
    adapt = cv2.adaptiveThreshold(
        gray_e, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, -5
    )
    if np.mean(adapt) > 127:
        adapt = cv2.bitwise_not(adapt)
    variants.append(adapt)

    # --- D: Highlight yellow/gold channel (loot numbers are often golden) ---
    b, g, r = cv2.split(big)
    yellowish = cv2.subtract(cv2.max(r, g), b)
    _, ymask = cv2.threshold(yellowish, 28, 255, cv2.THRESH_BINARY)
    ymask = cv2.morphologyEx(ymask, cv2.MORPH_CLOSE, k)
    variants.append(cv2.bitwise_not(ymask))

    return variants


def _collect_ocr_candidates(img_bgr, storage_mode):
    outs = []
    for bin_img in _variants_for_ocr(img_bgr, storage_mode):
        for psm in (7, 8):
            v = _tesseract_read_digits(bin_img, psm=psm)
            if v is not None and v >= 0:
                outs.append(v)
        v2 = _tesseract_read_digits_data(bin_img)
        if v2 is not None and v2 >= 0:
            outs.append(v2)
    return outs


def _pick_consensus(values, max_reasonable=2_500_000_000):
    """
    Pick a single value from several OCR attempts: bucket by nearest 1k (CoC uses
    whole numbers), take the mode bucket, then median within that bucket.
    """
    filtered = [v for v in values if 0 < v <= max_reasonable]
    if not filtered:
        return None
    if max(filtered) < 10_000:
        return int(round(median(filtered)))
    # Nearest-thousand buckets tolerate small digit errors across pipelines
    buckets = [round(v, -3) for v in filtered]

    winner, _ = Counter(buckets).most_common(1)[0]
    in_bucket = [v for v in filtered if round(v, -3) == winner]
    if not in_bucket:
        in_bucket = filtered
    return int(round(median(in_bucket)))


def is_unaffordable(region):
    """
    Checks if the cost text is RED.
    Threshold lowered to 15 to catch thin red fonts during UI animations.
    """
    ss = pyautogui.screenshot(region=region)
    img = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2BGR)
    lower_red = np.array([80, 80, 180]) 
    upper_red = np.array([160, 160, 255])
    mask = cv2.inRange(img, lower_red, upper_red)
    return np.sum(mask > 0) > 15

def get_number_local(region, storage_mode=False, samples=1, max_value=None):
    """
    Read a resource number from a screen region. Uses several binarization
    strategies and consensus to reduce Tesseract errors on CoC UI text.
    `samples`: multi-frame consensus when animations flicker (storage uses 2).
    `max_value`: drop OCR candidates above this (use MAX_LOOT_PER_RESOURCE on attack loot).
    """
    cap = max_value if max_value is not None else 2_500_000_000
    try:
        all_vals = []
        for attempt in range(2):
            all_vals.clear()
            n_frames = max(1, samples) if attempt == 0 else max(samples, 2)
            for _ in range(n_frames):
                ss = pyautogui.screenshot(region=region)
                img = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2BGR)
                batch = _collect_ocr_candidates(img, storage_mode)
                all_vals.extend(batch)
                if n_frames > 1:
                    time.sleep(0.06)

            picked = _pick_consensus(all_vals, max_reasonable=cap)
            if picked is not None:
                return picked

            nz = [v for v in all_vals if 0 < v <= cap]
            if nz:
                return int(round(median(nz)))

            if (
                attempt == 0
                and max_value is not None
                and all_vals
                and not any(v <= max_value for v in all_vals)
            ):
                time.sleep(0.14)
                continue
            return 0
    except Exception as e:
        print(f"OCR Error: {e}")
        return 0

def find_a_wall():
    for name in ("wall1", "wall2"):
        path = os.path.join(WALL_DIR, f"{name}.png")
        if os.path.exists(path):
            try:
                loc = pyautogui.locateOnScreen(path, confidence=0.74, grayscale=True)
                if loc:
                    status(
                        f"WALL MATCH: {name}.png",
                        "cyan",
                        phase="WALL DUMP",
                        finding=f"Clicked wall template {name}.png",
                    )
                    pyautogui.click(pyautogui.center(loc))
                    return True
            except:
                # If PyAutoGUI throws an ImageNotFoundException, safely ignore it 
                # and loop to the next wall image
                pass 
    return False

# --- LOGIC MODULES ---

def _wall_locate(name, grayscale=True):
    path = os.path.join(WALL_DIR, f"{name}.png")
    if not os.path.exists(path):
        status(f"MISSING WALL TEMPLATE: {name}.png", "red", phase="WALL DUMP")
        return None
    for confidence in (0.82, 0.74, 0.66, 0.58, 0.50, 0.42):
        try:
            loc = pyautogui.locateOnScreen(path, confidence=confidence, grayscale=grayscale)
            if loc:
                return loc
        except Exception:
            pass
    return None


def _wall_click(name, wait=0.35):
    loc = _wall_locate(name)
    if not loc:
        status(f"WALL UI NOT FOUND: {name}.png", "red", phase="WALL DUMP")
        return None
    point = pyautogui.center(loc)
    status(
        f"WALL CLICK: {name}.png at ({int(point.x)}, {int(point.y)})",
        "cyan",
        phase="WALL DUMP",
    )
    pyautogui.click(point)
    time.sleep(wait)
    return loc


def _wall_click_when_visible(
    name,
    *,
    timeout=8.0,
    initial_delay=0.5,
    poll_interval=0.25,
    wait=1.4,
):
    """Wait for a wall dialog button to render, then click it once.

    Selecting a resource triggers a short UI transition. A one-shot template
    lookup can run before the confirmation card has been painted, so this
    helper gives the dialog a small settling delay and then polls until the
    button appears or the timeout expires.
    """
    if initial_delay > 0:
        time.sleep(initial_delay)
    deadline = time.time() + timeout
    while time.time() < deadline:
        loc = _wall_locate(name)
        if loc:
            point = pyautogui.center(loc)
            status(
                f"WALL CLICK: {name}.png at ({int(point.x)}, {int(point.y)})",
                "cyan",
                phase="WALL DUMP",
            )
            pyautogui.click(point)
            time.sleep(wait)
            return loc
        time.sleep(poll_interval)
    status(f"WALL UI NOT FOUND: {name}.png", "red", phase="WALL DUMP")
    return None


def _click_item_template(name, timeout=8.0, wait=0.5, phase="WALL DUMP"):
    """Click a non-wall template and report it in the requested phase."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _click_item_template_once(name, wait=wait, phase=phase):
            return True
        time.sleep(0.25)
    status(f"ITEM NOT FOUND: {name}.png", "red", phase=phase)
    return False


def _locate_item_template(name, *, grayscale=True, confidences=None):
    path = os.path.join(ITEM_DIR, f"{name}.png")
    if confidences is None:
        confidences = (0.82, 0.74, 0.66, 0.58, 0.50)
    for confidence in confidences:
        try:
            loc = pyautogui.locateOnScreen(path, confidence=confidence, grayscale=grayscale)
        except Exception:
            loc = None
        if loc:
            return loc
    return None


def _click_item_template_once(
    name,
    wait=0.5,
    phase="WALL DUMP",
    *,
    grayscale=True,
    confidences=None,
):
    """Make one non-blocking template search and click if it is visible."""
    loc = _locate_item_template(name, grayscale=grayscale, confidences=confidences)
    if not loc:
        return False
    point = pyautogui.center(loc)
    status(
        f"ITEM CLICK: {name}.png at ({int(point.x)}, {int(point.y)})",
        "cyan",
        phase=phase,
    )
    pyautogui.click(point)
    time.sleep(wait)
    return True


def _locate_cleanup_template(name):
    """Locate cleanup buttons with color-sensitive, stricter matching.

    End Battle/Surrender are red while Return Home is green. The previous
    grayscale scan down to 0.50 confidence could cross-match those buttons.
    """
    return _locate_item_template(
        name,
        grayscale=False,
        confidences=CLEANUP_MATCH_CONFIDENCES,
    )


def _click_cleanup_template_once(name, wait=0.5, phase="CLEANUP"):
    """Click one cleanup template using the guarded cleanup matcher."""
    loc = _locate_cleanup_template(name)
    if not loc:
        return False
    point = pyautogui.center(loc)
    status(
        f"ITEM CLICK: {name}.png at ({int(point.x)}, {int(point.y)})",
        "cyan",
        phase=phase,
    )
    pyautogui.click(point)
    time.sleep(wait)
    return True


def _wall_cost_is_affordable(region, label):
    try:
        shot = pyautogui.screenshot(region=region)
        image = np.array(shot)
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        red_a = cv2.inRange(hsv, np.array([0, 70, 60]), np.array([15, 255, 255]))
        red_b = cv2.inRange(hsv, np.array([165, 70, 60]), np.array([179, 255, 255]))
        red_count = int(np.count_nonzero(red_a | red_b))

        # White numbers are bright and low-saturation. They are useful as a
        # sanity check, but red is the decisive unaffordable state.
        white = cv2.inRange(hsv, np.array([0, 0, 150]), np.array([179, 90, 255]))
        white_count = int(np.count_nonzero(white))
        total_pixels = max(1, image.shape[0] * image.shape[1])
        red_ratio = red_count / total_pixels

        # Save the exact region and masks so the next run can be inspected.
        cv2.imwrite(
            os.path.join(DEBUG_WALL_DIR, f"{label.lower()}_cost_region.png"),
            cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
        )
        cv2.imwrite(
            os.path.join(DEBUG_WALL_DIR, f"{label.lower()}_cost_red_mask.png"),
            red_a | red_b,
        )
        status(
            f"WALL {label} COST PIXELS: red={red_count} ({red_ratio:.1%}) white={white_count}",
            "white",
            phase="WALL DUMP",
        )
        # Small red speckles/outlines are not enough to mean unaffordable.
        # The number is considered red only when red occupies a substantial
        # portion of the exact number region.
        return red_ratio < 0.15
    except Exception:
        return False


def _wall_cost_states():
    # The fixed regions are the source of truth for affordability. Do not use
    # the Gold/Elixir card templates for the click location: at low matching
    # confidence, the nearly identical cards can cross-match and select Gold
    # when Elixir is the affordable resource.
    gold_green = _wall_cost_is_affordable(WALL_GOLD_COST_COLOR_REGION, "GOLD")
    elixir_green = _wall_cost_is_affordable(WALL_ELIXIR_COST_COLOR_REGION, "ELIXIR")
    status(
        f"WALL COST COLORS: Gold={'WHITE/OK' if gold_green else 'RED'} · Elixir={'WHITE/OK' if elixir_green else 'RED'}",
        "white",
        phase="WALL DUMP",
    )
    return gold_green, elixir_green, None, None


def _click_wall_resource(resource):
    """Click the selected wall resource using its calibrated cost region."""
    if resource == "gold":
        region = WALL_GOLD_COST_COLOR_REGION
        label = "GOLD"
    else:
        region = WALL_ELIXIR_COST_COLOR_REGION
        label = "ELIXIR"
    point = (region[0] + region[2] // 2, region[1] + region[3] // 2)
    status(
        f"WALL UPGRADE: selecting {label} at ({point[0]}, {point[1]})",
        "yellow" if resource == "gold" else "pink",
        phase="WALL DUMP",
        finding="Clicked from the matching affordability region",
    )
    pyautogui.click(*point)


def _wall_dump_cycle_impl():
    status(">>> INITIATING IMAGE-BASED WALL DUMP <<<", "purple", phase="WALL DUMP")
    preferred_resource = "gold"
    while True:
        g = get_number_local(GOLD_STORAGE_REGION, True, OCR_SAMPLES_STORAGE)
        e = get_number_local(ELIXIR_STORAGE_REGION, True, OCR_SAMPLES_STORAGE)
        if g < MIN_RESOURCES_TO_KEEP and e < MIN_RESOURCES_TO_KEEP:
            return
        if not find_a_wall():
            status("WALL DUMP STOP: no wall template found", "orange", phase="WALL DUMP")
            return
        if not _wall_click("wall upgrade_more_button", 0.8):
            status("WALL DUMP STOP: Upgrade More button not found", "red", phase="WALL DUMP")
            return
        # Start at one wall and increase one at a time. The add_10_walls
        # shortcut is intentionally not used. Four walls is a hard cap for
        # this storage setup because a fifth wall cannot be funded.
        if not _wall_click("add_wall", 0.45):
            status("WALL DUMP STOP: Add Wall button not found", "red", phase="WALL DUMP")
            return

        selected_walls = 1
        while selected_walls < MAX_WALLS_PER_GROUP:
            gold_green, elixir_green, _, _ = _wall_cost_states()
            if gold_green is None or elixir_green is None:
                status("WALL DUMP STOP: cost status could not be read", "red", phase="WALL DUMP")
                return
            if not gold_green and not elixir_green:
                _wall_click("remove_wall", 0.45)
                selected_walls -= 1
                break
            if not _wall_click("add_wall", 0.45):
                break
            selected_walls += 1
            gold_after, elixir_after, _, _ = _wall_cost_states()
            if gold_after is None or elixir_after is None:
                status("WALL DUMP STOP: cost status could not be read", "red", phase="WALL DUMP")
                return
            if not gold_after and not elixir_after:
                _wall_click("remove_wall", 0.45)
                selected_walls -= 1
                break

        status(
            f"WALL GROUP READY: {selected_walls} wall(s) selected",
            "green",
            phase="WALL DUMP",
        )

        gold_green, elixir_green, _, _ = _wall_cost_states()
        resource = None
        for candidate in (preferred_resource, "elixir" if preferred_resource == "gold" else "gold"):
            if (candidate == "gold" and gold_green) or (candidate == "elixir" and elixir_green):
                resource = candidate
                break
        if resource is None:
            status("WALL DUMP STOP: neither resource is affordable", "orange", phase="WALL DUMP")
            return
        _click_wall_resource(resource)
        time.sleep(0.6)
        if selected_walls == 1:
            # A single-wall upgrade shows the wall-specific confirmation card.
            confirmation_name = "wall_upgrade_confirmation"
            confirmation_clicked = _wall_click_when_visible(
                confirmation_name,
                timeout=8.0,
                initial_delay=0.5,
                poll_interval=0.25,
                wait=1.4,
            )
        else:
            # A multi-wall upgrade shows the green attack-style Okay button.
            # This template lives in item/, not item/wall/.
            confirmation_name = "attack_end_battle_confirm"
            confirmation_clicked = _click_item_template(
                confirmation_name,
                timeout=8.0,
                wait=1.2,
                phase="WALL DUMP",
            )
        if not confirmation_clicked:
            status(
                f"WALL DUMP STOP: {confirmation_name} confirmation not found",
                "red",
                phase="WALL DUMP",
            )
            return
        # Alternate the preferred resource after every completed group. This
        # forces a fresh affordability check for Elixir after a Gold group,
        # while still falling back to Gold when Elixir is unavailable.
        preferred_resource = "elixir" if resource == "gold" else "gold"
        status("WALL UPGRADE COMPLETE: rechecking storage and next wall", "green", phase="WALL DUMP")
        time.sleep(1.2)


def wall_dump_cycle():
    """Run wall maintenance with the status overlay hidden over the game."""
    overlay_was_visible = bool(overlay and overlay.root.state() != "withdrawn")
    if overlay_was_visible:
        status("WALL DUMP: hiding overlay so wall templates remain clickable", "cyan", phase="WALL DUMP")
        overlay.hide()
    try:
        return _wall_dump_cycle_impl()
    finally:
        if overlay_was_visible and overlay:
            overlay.show()
            status("WALL DUMP: overlay restored", "cyan", phase="MAINTENANCE")

def _locate_return_home():
    """Return the first Return Home image match, or None for this check."""
    for confidence in (0.90, 0.84, 0.78):
        return_home_loc = find_item(
            "return_home",
            confidence=confidence,
            region=None,
            grayscale=False,
        )
        if not return_home_loc:
            continue
        status("RETURN HOME IMAGE FOUND", "white", phase="CLEANUP")
        return return_home_loc
    return None


def _click_return_home(return_home_loc):
    point = pyautogui.center(return_home_loc)
    status(
        f"RETURN HOME CLICK: ({int(point.x)}, {int(point.y)})",
        "green",
        phase="HOME",
    )
    pyautogui.click(point)
    time.sleep(POST_RETURN_HOME_WAIT)


def wait_for_return_home(poll_interval=RETURN_HOME_POLL_INTERVAL):
    """Poll every second until the validated Return Home image is found."""
    status(
        "CLEANUP: Waiting for Return Home...",
        "orange",
        phase="CLEANUP",
        finding="Polling return_home.png every second; click only after image confirmation",
    )

    stable_point = None
    stable_hits = 0
    while True:
        return_home_loc = _locate_cleanup_template("return_home")
        if return_home_loc:
            point = pyautogui.center(return_home_loc)
            if stable_point and abs(point.x - stable_point.x) <= 30 and abs(point.y - stable_point.y) <= 30:
                stable_hits += 1
            else:
                stable_point = point
                stable_hits = 1
            status(
                f"RETURN HOME CANDIDATE: ({int(point.x)}, {int(point.y)}) stable {stable_hits}/{RETURN_HOME_STABLE_HITS}",
                "white",
                phase="CLEANUP",
            )
            if stable_hits >= RETURN_HOME_STABLE_HITS:
                status("CLEANUP: Confirmed Return Home via stable template.", "green", phase="HOME")
                _click_return_home(return_home_loc)
                return True
        else:
            stable_point = None
            stable_hits = 0
        time.sleep(poll_interval)


def finish_attack():
    """Wait 45 seconds, then follow the End Battle/Return Home state flow."""
    status(
        f"ATTACK TIMER: waiting {ATTACK_WAIT_BEFORE_RETURN_HOME:.0f}s before Return Home check",
        "orange",
        phase="ATTACK",
        finding="Tracking elapsed attack time before cleanup",
    )
    started = time.time()
    deadline = started + ATTACK_WAIT_BEFORE_RETURN_HOME
    while time.time() < deadline:
        remaining = max(0.0, deadline - time.time())
        status(
            f"ATTACK TIMER: {remaining:.0f}s remaining",
            "white",
            phase="ATTACK",
        )
        time.sleep(min(1.0, remaining))

    elapsed = time.time() - started
    status(
        f"ATTACK TIMER: {elapsed:.1f}s elapsed — checking Return Home",
        "cyan",
        phase="CLEANUP",
    )
    end_battle_clicked = False
    confirmation_clicked = False

    status(
        "CLEANUP: Return Home polling started",
        "orange",
        phase="CLEANUP",
        finding="Checking return_home.png every second",
    )
    while True:
        poll_started = time.time()

        if not end_battle_clicked:
            # Return Home must be checked first. The old order allowed a loose
            # grayscale End Battle match to win even when Return Home was the
            # actual visible button, sending the state machine into a
            # confirmation wait that could never succeed.
            return_home_loc = _locate_cleanup_template("return_home")
            if return_home_loc:
                status("RETURN HOME FOUND — clicking it", "green", phase="HOME")
                _click_return_home(return_home_loc)
                return

            # Only use strict, color-sensitive matches for End Battle. Either
            # red End Battle visual is acceptable.
            for end_name in ("end_battle", "end_battle_2"):
                if _click_cleanup_template_once(end_name, wait=0.8, phase="CLEANUP"):
                    end_battle_clicked = True
                    status(
                        f"END BATTLE: clicked {end_name}.png — now finding confirmation",
                        "cyan",
                        phase="CLEANUP",
                    )
                    break

        elif not confirmation_clicked:
            # The battle can finish on its own while the confirmation dialog
            # is still appearing. Check Return Home first so we do not wait
            # forever for a confirmation button that will never exist.
            return_home_loc = _locate_cleanup_template("return_home")
            if return_home_loc:
                status("RETURN HOME FOUND — clicking it", "green", phase="HOME")
                _click_return_home(return_home_loc)
                return

            # If Return Home is not visible yet, look for the End Battle
            # confirmation and then continue polling Return Home normally.
            if _click_cleanup_template_once(
                "attack_end_battle_confirm",
                wait=1.0,
                phase="CLEANUP",
            ):
                confirmation_clicked = True
                status(
                    "END BATTLE CONFIRMED — now finding Return Home",
                    "green",
                    phase="CLEANUP",
                    finding="return_home.png will be checked every second",
                )
            elif find_item("attack1", confidence=0.88, region=None, grayscale=False):
                # If a false End Battle match clicked Return Home directly,
                # the game is already back at the home screen and no
                # confirmation dialog can appear. Do not wait forever.
                status(
                    "CLEANUP: already back on the home screen; confirmation was skipped",
                    "green",
                    phase="HOME",
                )
                return

        else:
            return_home_loc = _locate_cleanup_template("return_home")
            if return_home_loc:
                status("RETURN HOME FOUND — clicking it", "green", phase="HOME")
                _click_return_home(return_home_loc)
                return

        # Keep the state checks on a one-second cadence, accounting for the
        # time spent scanning and clicking during this poll.
        time.sleep(max(0.0, RETURN_HOME_POLL_INTERVAL - (time.time() - poll_started)))
    
def _recover_from_deploy_abort(label):
    status(
        f"DEPLOY ABORTED: {label} — recovering to home",
        "red",
        phase="CLEANUP",
        finding="Waiting for Return Home instead of relaunching from battle",
    )
    wait_for_return_home()


def wait_for_home_screen(timeout=HOME_CONFIRM_TIMEOUT):
    """Confirm the home screen before any launch click is attempted."""
    deadline = time.time() + timeout
    hits = 0
    while time.time() < deadline:
        loc = find_item("attack1", confidence=0.82, region=None, grayscale=False)
        if loc:
            hits += 1
            status(
                f"HOME SCREEN CANDIDATE: attack1.png stable {hits}/{HOME_CONFIRM_STABLE_HITS}",
                "white",
                phase="HOME",
            )
            if hits >= HOME_CONFIRM_STABLE_HITS:
                return True
        else:
            hits = 0
        time.sleep(0.5)
    return False


def execute_attack():
    try:
        if overlay:
            overlay.hide()
        status(
            "DEPLOY: updated coordinate sequence (overlay hidden)",
            "orange",
            phase="ATTACK",
            finding="Troop 1=50 · Troop 2=10 · Spell 1=5 · Spell 2=1",
        )

        for template, points in (
            ("attack_troop_1", TROOP_1_COORDS),
            ("attack_troop_2", TROOP_2_COORDS),
        ):
            status(
                f"DEPLOY: locating {template}.png before {len(points)} battlefield clicks",
                "orange",
                phase="ATTACK",
                finding="No battlefield clicks will occur until this troop image is clicked",
            )
            if not find_click_template_until(template, timeout_s=DEPLOY_TEMPLATE_TIMEOUT, grayscale=False):
                _recover_from_deploy_abort(template)
                return
            status(
                f"DEPLOY: {template}.png selected — sending {len(points)} clicks",
                "green",
                phase="ATTACK",
            )
            click_deploy_line(points)

        if not find_click_template_until("attack_spell_1", timeout_s=DEPLOY_TEMPLATE_TIMEOUT, grayscale=False):
            _recover_from_deploy_abort("attack_spell_1")
            return
        click_deploy_line(SPELL_1_COORDS)

        if not find_click_template_until("attack_spell_2", timeout_s=DEPLOY_TEMPLATE_TIMEOUT, grayscale=False):
            _recover_from_deploy_abort("attack_spell_2")
            return
        pyautogui.click(*SPELL_2_DROP)
        time.sleep(0.2)

        if not find_click_template_until("attack_troop_3", timeout_s=DEPLOY_TEMPLATE_TIMEOUT, grayscale=False):
            _recover_from_deploy_abort("attack_troop_3")
            return
        pyautogui.click(*SINGLE_DROP)
        time.sleep(0.25)

        for index, hero_name in enumerate(
            ("attack_hero_1", "attack_hero_2", "attack_hero_3", "attack_hero_4"),
            start=1,
        ):
            status(f"HERO {index}: {hero_name}.png", "cyan", phase="ATTACK")
            if not find_click_template_until(hero_name, timeout_s=HERO_DEPLOY_TEMPLATE_TIMEOUT, grayscale=False):
                status(f"SKIP HERO: {hero_name} not found", "orange", phase="ATTACK")
                continue
            pyautogui.click(*HERO_DEPLOY_COORDS[index - 1])
            time.sleep(0.35)

        finish_attack()
    finally:
        if overlay:
            overlay.show()

# --- DEBUG VISUALS ---
SHOW_CLICK_MARKERS = True
SHOW_OCR_REGION_MARKERS = True


def _flash_box(x, y, width, height, color, duration=350):
    if not overlay:
        return

    def show():
        try:
            win = tk.Toplevel(overlay.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True, "-alpha", 0.85)
            try:
                win.attributes("-transparentcolor", "black")
            except tk.TclError:
                pass
            canvas = tk.Canvas(win, width=max(4, width), height=max(4, height), bg="black", highlightthickness=0)
            canvas.create_rectangle(2, 2, max(2, width - 2), max(2, height - 2), outline=color, width=4)
            canvas.pack()
            win.geometry(f"{max(4, width)}x{max(4, height)}+{int(x)}+{int(y)}")
            win.after(duration, win.destroy)
        except Exception:
            pass

    try:
        overlay.root.after(0, show)
    except Exception:
        pass


_original_click = pyautogui.click


def _click_with_marker(*args, **kwargs):
    result = _original_click(*args, **kwargs)
    # Click markers are useful for launch/wall debugging, but creating a GUI
    # window for every troop click makes a 50-click wave unnecessarily slow.
    attack_overlay_hidden = overlay is not None and overlay.root.state() == "withdrawn"
    if SHOW_CLICK_MARKERS and not attack_overlay_hidden:
        try:
            if len(args) >= 2 and isinstance(args[0], (int, float)):
                x, y = args[0], args[1]
            elif args and hasattr(args[0], "x"):
                x, y = args[0].x, args[0].y
            else:
                x, y = pyautogui.position()
            _flash_box(int(x) - 16, int(y) - 16, 32, 32, "#ff3030", 300)
        except Exception:
            pass
    return result


pyautogui.click = _click_with_marker

_original_get_number_local = get_number_local


def get_number_local(region, *args, **kwargs):
    if SHOW_OCR_REGION_MARKERS:
        _flash_box(region[0], region[1], region[2], region[3], "#00e5ff", 900)
    return _original_get_number_local(region, *args, **kwargs)


# --- ENGINE ---

def on_press(key):
    if key == keyboard.Key.esc: os._exit(0)
    if key == keyboard.Key.page_up: global start_requested; start_requested = True
    if key == keyboard.Key.f12 and overlay:
        overlay.root.after(0, open_calibration_menu)

keyboard.Listener(on_press=on_press).start()

def main_logic():
    global start_requested, attack_count
    while not start_requested:
        time.sleep(0.1)

    status(
        "Bot armed — main loop running",
        "green",
        phase="HOME",
        finding="Esc=quit · Storage checked after each attack · Loot cap enforced in OCR",
    )

    maintenance_check_pending = True

    while True:
        try:
            # Maintenance Check
            maintenance_due = (
                maintenance_check_pending
                or attack_count >= 1
                if CHECK_STORAGE_AFTER_EVERY_ATTACK
                else maintenance_check_pending or attack_count >= 10
            )
            if maintenance_due:
                maintenance_check_pending = False
                status(
                    "MAINTENANCE: Storage Check...",
                    "white",
                    phase="MAINTENANCE",
                    finding=f"Reading storage OCR · wall dump if over {WALL_DUMP_THRESHOLD:,}",
                )
                time.sleep(MAINTENANCE_UI_WAIT)

                g_st = get_number_local(GOLD_STORAGE_REGION, True, OCR_SAMPLES_STORAGE)
                e_st = get_number_local(ELIXIR_STORAGE_REGION, True, OCR_SAMPLES_STORAGE)
                status(
                    f"STORAGE OCR: Gold {g_st:,} · Elixir {e_st:,}",
                    "white",
                    phase="MAINTENANCE",
                    finding=f"Dump walls if either > {WALL_DUMP_THRESHOLD:,}",
                )

                if g_st > WALL_DUMP_THRESHOLD or e_st > WALL_DUMP_THRESHOLD:
                    wall_dump_cycle()
                    
                    # --- POST-DUMP VERIFICATION ---
                    status(
                        "VERIFYING: Did the dump succeed?",
                        "white",
                        phase="MAINTENANCE",
                        finding="Re-read storage — expect below wall-dump threshold",
                    )
                    time.sleep(POST_DUMP_VERIFY_WAIT)

                    g_post = get_number_local(GOLD_STORAGE_REGION, True, OCR_SAMPLES_STORAGE)
                    e_post = get_number_local(ELIXIR_STORAGE_REGION, True, OCR_SAMPLES_STORAGE)
                    status(
                        f"POST-DUMP STORAGE: Gold {g_post:,} · Elixir {e_post:,}",
                        "white",
                        phase="MAINTENANCE",
                        finding="Compare to threshold — success if both below",
                    )

                    if g_post > WALL_DUMP_THRESHOLD or e_post > WALL_DUMP_THRESHOLD:
                        status(
                            "DUMP ABORTED: Retrying in 1 attack.",
                            "red",
                            phase="MAINTENANCE",
                            finding="Storage still high — attack_count set to 9",
                        )
                        attack_count = 9 
                    else:
                        status(
                            "DUMP SUCCESS: Resources cleared.",
                            "green",
                            phase="HOME",
                            finding="attack_count reset to 0",
                        )
                        attack_count = 0 
                else:
                    status(
                        "MAINTENANCE: Need more loot. Checking again next attack.",
                        "orange",
                        phase="HOME",
                        finding=f"Storage under {WALL_DUMP_THRESHOLD:,} — no dump",
                    )

            # Step 1: Launch sequence from a confirmed home screen. Popup and
            # banner automation is intentionally disabled.
            if not wait_for_home_screen():
                status(
                    "LAUNCH BLOCKED: home screen not confirmed",
                    "red",
                    phase="HOME",
                    finding="Return Home was not verified; no attack1 click will be attempted",
                )
                time.sleep(2.0)
                continue

            status(
                "STATE: Launching Attack Sequence (attack1 → attack2 → attack3)",
                "white",
                phase="LAUNCH",
                finding="Templates in item/: attack1.png, attack2.png, attack3.png",
            )
            if not launch_attack_from_home():
                status(
                    "LAUNCH ABORT: could not find attack1/2/3 templates — fix item/ PNGs",
                    "red",
                    phase="LAUNCH",
                    finding="Check ITEM_DIR path printed at startup",
                )
                time.sleep(2.5)
                continue

            searching = True
            zero_ocr_attempts = 0
            while searching:
                base_loaded = False
                
                # Wait for base to load using the Dragon icon
                for i in range(40):  # ~40 * poll — cloud / load timeout
                    if find_item("dragon", confidence=0.75):
                        status(
                            "ANALYSIS: Base Detected.",
                            "cyan",
                            phase="LOOT CHECK",
                            finding="dragon.png seen — base loaded, OCR next",
                        )
                        base_loaded = True
                        break
                    if i % 4 == 0:
                        status(
                            f"Cloud / load: attempt {i + 1}/40 — waiting for dragon.png",
                            "white",
                            phase="CLOUD / LOAD",
                            finding="Template item/dragon.png @ 0.75 · still searching or loading",
                        )
                    time.sleep(CLOUD_SEARCH_POLL)

                if not base_loaded:
                    status(
                        "TIMEOUT: No base found.",
                        "red",
                        phase="LAUNCH",
                        finding="No dragon match — retrying launch from home",
                    )
                    break # Jumps back to Step 1 loop

                # Base loaded, check resources
                time.sleep(LOOT_OCR_SETTLE)
                loot_gold = get_number_local(
                    GOLD_REGION, False, OCR_SAMPLES_LOOT, MAX_LOOT_PER_RESOURCE
                )
                loot_elixir = get_number_local(
                    ELIXIR_REGION, False, OCR_SAMPLES_LOOT, MAX_LOOT_PER_RESOURCE
                )
                total = loot_gold + loot_elixir
                status(
                    f"LOOT: Gold ={loot_gold:,}, Elixir = {loot_elixir:,}",
                    "cyan",
                    phase="LOOT CHECK",
                    finding=f"OCR regions gold/elixir · cap {MAX_LOOT_PER_RESOURCE:,} each",
                )

                # OCR zero handling: retry once, then move to the next base.
                if total == 0:
                    zero_ocr_attempts += 1
                    # Give the base a couple of frames to finish rendering. If
                    # OCR is still zero after that, do not loop forever: move
                    # to the next base instead.
                    if zero_ocr_attempts < 2:
                        continue

                    status(
                        "OCR ZERO: advancing to next base",
                        "orange",
                        phase="NEXT BASE",
                        finding="Gold and elixir stayed at 0 after two reads",
                    )
                    next_btn = find_item("next", confidence=0.75)
                    if next_btn:
                        pyautogui.click(pyautogui.center(next_btn))
                    else:
                        pyautogui.click(*NEXT_BASE_CLICK)
                    zero_ocr_attempts = 0
                    time.sleep(NEXT_BASE_WAIT)
                    continue

                zero_ocr_attempts = 0

                status(
                    f"LOOT total {total:,} vs threshold {LOOT_THRESHOLD:,}",
                    "cyan",
                    phase="DECISION",
                    finding="Attack if ≥ threshold · else Next base",
                )

                # Evaluate Loot — require dragon + loot again before committing to attack
                if total >= LOOT_THRESHOLD:
                    time.sleep(0.15)
                    if not find_item("dragon", confidence=0.75):
                        status(
                            "SKIP ATTACK: dragon.png not visible before deploy",
                            "orange",
                            phase="DECISION",
                            finding="Re-scan next base",
                        )
                        next_btn = find_item("next", confidence=0.75)
                        if next_btn:
                            pyautogui.click(pyautogui.center(next_btn))
                        else:
                            pyautogui.click(*NEXT_BASE_CLICK)
                        time.sleep(NEXT_BASE_WAIT)
                        continue
                    execute_attack()
                    attack_count += 1
                    searching = False # Breaks search loop to return home
                else:
                    status(
                        "SKIPPING: Loot too low.",
                        "orange",
                        phase="NEXT BASE",
                        finding="Click next.png or fallback (1588,842)",
                    )
                    next_btn = find_item("next", confidence=0.75)
                    if next_btn:
                        pyautogui.click(pyautogui.center(next_btn))
                    else:
                        # Fallback coordinate if next.png isn't found
                        pyautogui.click(*NEXT_BASE_CLICK)
                    time.sleep(NEXT_BASE_WAIT)
        except Exception as exc:
            status(
                f"MAIN LOOP ERROR: {exc}",
                "red",
                phase="ERROR",
                finding="Bot paused briefly; no banner or exit automation is running",
            )
            time.sleep(2.0)

if __name__ == "__main__":
    print("[INFO] Running standalone finalworking_version.py")
    print(f"[INFO] ITEM_DIR = {ITEM_DIR}")
    print(f"[INFO] WALL_DIR = {WALL_DIR}")
    overlay = StatusOverlay()
    threading.Thread(target=main_logic, daemon=True).start()
    overlay.root.mainloop()
