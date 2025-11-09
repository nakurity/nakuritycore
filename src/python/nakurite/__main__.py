"""
record_input_and_screen.py

Records screen video and overlays live mouse/keyboard events. Also writes events to CSV.

USAGE:
  1) pip install pynput mss opencv-python numpy
  2) python record_input_and_screen.py
  3) Press ESC to stop recording.

LEGAL / ETHICS:
  - Run only on machines you own or where you have explicit consent.
  - This script is NOT stealthy — it prints status to the console and uses Esc to stop.

"""
import threading
import time
import csv
import os
from datetime import datetime
from collections import deque

import numpy as np
import cv2
import mss
from pynput import mouse, keyboard

# --- Config ---
FPS = 15                      # Video frames per second
RECENT_EVENTS = 8             # How many recent events to overlay
VIDEO_CODEC = "mp4v"          # FourCC codec
VIDEO_SCALE = 1.0             # optional scale (1.0 = native resolution)
OUTPUT_DIR = "."              # directory for outputs

# --- Globals / thread-safe structures ---
event_lock = threading.Lock()
recent_events = deque(maxlen=RECENT_EVENTS)  # (timestamp_str, type, desc)
current_mouse_pos = (0, 0)
stop_event = threading.Event()

# Prepare output filenames
now = datetime.now().strftime("%Y%m%d_%H%M%S")
video_filename = os.path.join(OUTPUT_DIR, f"recording_{now}.mp4")
csv_filename = os.path.join(OUTPUT_DIR, f"events_{now}.csv")

# --- Event logging ---
def write_event_to_csv_row(writer, timestamp, source, description):
    writer.writerow([timestamp, source, description])

# --- Input callbacks ---
def on_move(x, y):
    global current_mouse_pos
    with event_lock:
        current_mouse_pos = (int(x), int(y))
        ts = datetime.now().isoformat(timespec='milliseconds')
        recent_events.appendleft((ts, 'MOUSE_MOVE', f"({int(x)},{int(y)})"))

def on_click(x, y, button, pressed):
    with event_lock:
        ts = datetime.now().isoformat(timespec='milliseconds')
        action = "DOWN" if pressed else "UP"
        desc = f"{button} {action} @({int(x)},{int(y)})"
        recent_events.appendleft((ts, 'MOUSE_CLICK', desc))
        # persist to CSV immediately
        csv_writer_lock.acquire()
        try:
            write_event_to_csv_row(csv_writer, ts, 'MOUSE_CLICK', desc)
            csv_file.flush()
        finally:
            csv_writer_lock.release()

def on_scroll(x, y, dx, dy):
    with event_lock:
        ts = datetime.now().isoformat(timespec='milliseconds')
        desc = f"scroll dx={dx} dy={dy} @({int(x)},{int(y)})"
        recent_events.appendleft((ts, 'MOUSE_SCROLL', desc))
        csv_writer_lock.acquire()
        try:
            write_event_to_csv_row(csv_writer, ts, 'MOUSE_SCROLL', desc)
            csv_file.flush()
        finally:
            csv_writer_lock.release()

def on_key_press(key):
    try:
        kdesc = key.char
    except AttributeError:
        kdesc = str(key)
    ts = datetime.now().isoformat(timespec='milliseconds')
    desc = f"PRESS {kdesc}"
    with event_lock:
        recent_events.appendleft((ts, 'KEY_DOWN', desc))
    # write to CSV
    csv_writer_lock.acquire()
    try:
        write_event_to_csv_row(csv_writer, ts, 'KEY_DOWN', desc)
        csv_file.flush()
    finally:
        csv_writer_lock.release()
    # stop trigger (Esc)
    if key == keyboard.Key.esc:
        print("Esc pressed — stopping recording...")
        stop_event.set()
        # Returning False from listener's callback would stop only that listener.
        # We'll set stop_event to gracefully stop everything.

def on_key_release(key):
    try:
        kdesc = key.char
    except AttributeError:
        kdesc = str(key)
    ts = datetime.now().isoformat(timespec='milliseconds')
    desc = f"RELEASE {kdesc}"
    with event_lock:
        recent_events.appendleft((ts, 'KEY_UP', desc))
    csv_writer_lock.acquire()
    try:
        write_event_to_csv_row(csv_writer, ts, 'KEY_UP', desc)
        csv_file.flush()
    finally:
        csv_writer_lock.release()

# --- CSV writer setup ---
csv_file = open(csv_filename, 'w', newline='', encoding='utf-8')
csv_writer = csv.writer(csv_file)
csv_writer.writerow(['timestamp', 'source', 'description'])
csv_writer_lock = threading.Lock()

# --- Screen capture / compositor thread ---
def screen_record_loop():
    print("Screen recording thread started.")
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor. index 1 is primary on mss
        width = int(monitor['width'] * VIDEO_SCALE)
        height = int(monitor['height'] * VIDEO_SCALE)
        fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)
        out = cv2.VideoWriter(video_filename, fourcc, FPS, (width, height))
        last_frame_time = time.time()
        frame_interval = 1.0 / FPS

        try:
            while not stop_event.is_set():
                t0 = time.time()
                sct_img = sct.grab(monitor)
                # Convert to numpy BGR image
                frame = np.array(sct_img)
                # mss returns BGRA, convert to BGR
                if frame.shape[2] == 4:
                    frame = frame[:, :, :3]
                # optional resize
                if VIDEO_SCALE != 1.0:
                    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

                # overlay: draw mouse cursor & recent events
                with event_lock:
                    mx, my = current_mouse_pos
                    # scale mouse pos if recording scaled
                    if VIDEO_SCALE != 1.0:
                        mx = int(mx * VIDEO_SCALE)
                        my = int(my * VIDEO_SCALE)

                    # Draw circle for mouse cursor
                    cv2.circle(frame, (mx, my), 12, (0, 255, 255), thickness=2)
                    # small center dot
                    cv2.circle(frame, (mx, my), 3, (0, 255, 255), thickness=-1)

                    # Draw recent events in top-left
                    y0 = 30
                    for i, (ts, src, desc) in enumerate(list(recent_events)[:RECENT_EVENTS]):
                        text = f"{ts.split('T')[-1]} {src}: {desc}"
                        # putText params: img, text, org, font, fontScale, color, thickness, lineType
                        cv2.putText(frame, text, (10, y0 + i * 22),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

                    # small status bar
                    fps_est = 1.0 / max(1e-6, (t0 - last_frame_time))
                    status = f"Recording — FPS approx: {fps_est:.1f} — Press Esc to stop"
                    cv2.putText(frame, status, (10, height - 10),
                                cv2.FONT_HERSHEY_DUPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

                out.write(frame)
                last_frame_time = t0

                # sleep to match FPS (account for time taken)
                elapsed = time.time() - t0
                to_sleep = frame_interval - elapsed
                if to_sleep > 0:
                    time.sleep(to_sleep)
        finally:
            out.release()
    print("Screen recording thread finished.")

# --- Start listeners ---
def start_listeners():
    # mouse listener
    mouse_listener = mouse.Listener(
        on_move=on_move,
        on_click=on_click,
        on_scroll=on_scroll)
    mouse_listener.start()

    # keyboard listener
    keyboard_listener = keyboard.Listener(
        on_press=on_key_press,
        on_release=on_key_release)
    keyboard_listener.start()

    return mouse_listener, keyboard_listener

# --- Main ---
def main():
    print("Starting input + screen recorder.")
    print("Ensure you have consent to record inputs on this machine.")
    print(f"Video -> {video_filename}")
    print(f"Events CSV -> {csv_filename}")
    print("Press Esc to stop recording.")

    # Start listeners
    m_listener, k_listener = start_listeners()

    # Start recording thread
    recorder_thread = threading.Thread(target=screen_record_loop, daemon=True)
    recorder_thread.start()

    # Wait until stopped
    try:
        while not stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("KeyboardInterrupt received — stopping.")
        stop_event.set()

    # clean up: stop listeners
    try:
        m_listener.stop()
    except Exception:
        pass
    try:
        k_listener.stop()
    except Exception:
        pass

    # give recorder thread time to finish
    recorder_thread.join(timeout=5.0)

    # close CSV
    csv_file.close()
    print("Recording saved.")
    print(f"Video: {video_filename}")
    print(f"Event log: {csv_filename}")

if __name__ == "__main__":
    main()
