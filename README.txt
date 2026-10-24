Clash of Clans bot package
===========================

Run from this folder:

    python finalworking_version.py

Controls:

    PAGE UP  Arm/start the bot
    F12      Open the click-sequence calibration menu
    ESC      Stop the bot

The bot loads captured_coordinates.json and all image templates from the
local item/ folder. The package is self-contained and does not import the
older cocv*.py files.

Calibration:

1. Start finalworking_version.py without pressing PAGE UP.
2. Click Edit click sequences in the overlay, or press F12.
3. Set a click count for only the sequence you want to recapture.
4. Click Capture, move to the game screen, and make exactly that many clicks.
5. The updated values are saved to captured_coordinates.json.

Disabled automation:

- No banner/cancel detection or automatic banner closing.
- No reconnect watchdog or app restart automation.
- After troop deployment, the bot tracks a 45-second attack wait.
- Every second after that wait it checks end_battle.png, end_battle_2.png, and
  return_home.png. If either End Battle image is found, it clicks that image,
  clicks attack_end_battle_confirm.png, then keeps checking return_home.png
  every second until it is found. If Return Home is found first, it clicks it
  immediately.
