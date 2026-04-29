import os
import time
import tkinter as tk
from PIL import Image, ImageTk
from picamera2 import Picamera2
import traceback

from clothing_recognizer import recognize_clothing_item
from inventory_db import init_db, add_item

PHOTO_DIR = "photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

# --- Camera ---
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration())
picam2.start()

# --- DB ---
init_db()

# --- GUI ---
root = tk.Tk()
root.title("Wardrobe Camera")

# Fullscreen can fail on some Pi touchscreen setups; fallback to fixed size
try:
    root.attributes("-fullscreen", True)   # <-- must be a CALL, not assignment
except Exception:
    root.geometry("480x640")               # common 3.5" resolution
    root.resizable(False, False)

status_var = tk.StringVar()
status_var.set("Ready")  # <-- must be a CALL

preview_label = tk.Label(root)
preview_label.pack(pady=10)

status_label = tk.Label(root, textvariable=status_var, font=("Arial", 14))
status_label.pack(pady=5)

button_frame = tk.Frame(root)
button_frame.pack(pady=10)

_preview_imgtk = None  # keep reference so Tk image doesn't get garbage-collected


def update_preview():
    global _preview_imgtk
    try:
        frame = picam2.capture_array()
        img = Image.fromarray(frame).resize((480, 320))
        _preview_imgtk = ImageTk.PhotoImage(img)
        preview_label.configure(image=_preview_imgtk)
    except Exception as e:
        status_var.set(f"Preview error: {e}")

    root.after(33, update_preview)  # ~30 FPS


def capture_image():
    # Small delay helps exposure stabilize
    time.sleep(0.4)

    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(PHOTO_DIR, f"capture_{ts}.jpg")

    try:
        status_var.set("Capturing...")
        root.update_idletasks()

        frame = picam2.capture_array()
        img = Image.fromarray(frame)
        if img.mode !="RGB":
            img = img.convert("RGB")
        img.save(path, "JPEG", quality=95)

        status_var.set("Processing...")
        root.update_idletasks()

        item = recognize_clothing_item(path)

        item_id = add_item(
            label=item["label"],
            category=item["category"],
            color=item["color"],
            warmth=int(item["warmth"]),
            waterproof=int(item["waterproof"]),
            formality=int(item["formality"]),
            image_path=path,
        )

        status_var.set(f"Added (id={item_id}): {item['label']}")

    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
        status_var.set(f"Error: {e}")


def exit_app():
    status_var.set("Exiting...")
    root.update_idletasks()
    try:
        picam2.stop()
    except Exception:
        pass
    root.destroy()


capture_button = tk.Button(
    button_frame,
    text="CAPTURE",
    command=capture_image,
    font=("Arial", 20),
    height=2,
    width=12,
    bg="green",
    fg="white",
)
capture_button.grid(row=0, column=0, padx=10)

exit_button = tk.Button(
    button_frame,
    text="EXIT",
    command=exit_app,
    font=("Arial", 20),
    height=2,
    width=8,
    bg="red",
    fg="white",
)
exit_button.grid(row=0, column=1, padx=10)

# Escape / q to exit
root.bind("<Escape>", lambda e: exit_app())
root.bind("q", lambda e: exit_app())
root.bind("Q", lambda e: exit_app())

update_preview()
root.mainloop()