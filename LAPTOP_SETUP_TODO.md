# PPParty Laptop Setup — Get the Webcam Working

Quick checklist to get MediaPipe webcam tracking running on the laptop.
The addon itself doesn't need a special Python — it uses Blender's built-in one.
But the **webcam tracker** (MediaPipe sender) is a separate Python script
that runs outside Blender and needs its own Python with three libraries installed.

If "Start Webcam" does nothing, it's almost always because that second Python
isn't set up. Do the steps below in order.

---

## What you're building

A folder at `~/.ppparty/venv/` — a private Python environment that lives in your
home directory, so it works no matter how you installed the PPParty addon (zip,
dev folder, doesn't matter). The addon knows to look there first.

Three libraries go inside it:
- **mediapipe** — the face + body tracking model
- **opencv-python** — talks to the webcam
- **numpy** — math under the hood

That's it. Nothing else on the laptop changes.

---

## Step 1 — Check if Python 3.11 is installed

Open Terminal and run:

```bash
python3.11 --version
```

- **If it prints `Python 3.11.x`** → skip to Step 3.
- **If it says "command not found"** → go to Step 2.

(3.10 and 3.12 also work. 3.13 is too new for MediaPipe as of April 2026.
3.9 works but is aging out — 3.11 is the sweet spot.)

---

## Step 2 — Install Python 3.11 (only if needed)

Go to [python.org/downloads](https://www.python.org/downloads/) and grab the
macOS installer for 3.11.x. Run it, click through defaults.

When it finishes, close Terminal, reopen it, and re-run the check from Step 1.
Should now print the version.

---

## Step 3 — Create the PPParty Python environment

Copy-paste these two lines into Terminal, one at a time:

```bash
mkdir -p ~/.ppparty
python3.11 -m venv ~/.ppparty/venv
```

First line makes a hidden folder in your home directory called `.ppparty`.
Second line builds a private Python inside it. Takes about 10 seconds.
Nothing prints when it's done — no news is good news.

---

## Step 4 — Install the three libraries

One command. This takes 2–5 minutes depending on your internet — it's
downloading ~300MB of MediaPipe models and OpenCV:

```bash
~/.ppparty/venv/bin/pip install mediapipe opencv-python numpy
```

You'll see a wall of green and yellow text. If the last line says
`Successfully installed mediapipe-… opencv-python-… numpy-…` you're done.

**If pip complains about SSL or certificates:** run this first, then retry:
```bash
/Applications/Python\ 3.11/Install\ Certificates.command
```

---

## Step 5 — Test the tracker by itself

Before opening Blender, prove the tracker works on its own. In Terminal:

```bash
~/.ppparty/venv/bin/python ~/Desktop/DR_BAYUS/SOFTWARE/PPPARTY/mediapipe_sender.py
```

**What you should see:**
- Your webcam's green light turns on
- A preview window pops up with your face
- Green dots appear on your face, cyan lines on your body
- Bottom-left corner says `FPS: 29.0  FACE | BODY`

Press **`q`** in the preview window to quit.

If you got all that, the laptop is ready. Proceed to Step 6.

---

## Step 6 — Run PPParty in Blender

1. Install the latest zip via Blender's Preferences → Add-ons → Install…
   (use `PPPARTY_v1.0.0-alpha.13.zip` or the landmark
   `PPPARTY_v1.0.0-alpha.12-marionette-body.zip`)
2. Open the PPPARTY N-panel
3. Click **Create Marionette**
4. In the Connect section, make sure "Show Tracker Window" is checked
5. Click **Start Webcam**

Puppet should start moving within 1–2 seconds.

---

## Troubleshooting

**"Start Webcam" button does nothing / no preview window appears**
→ Python environment missing. Re-run Steps 3 and 4.

**Preview window opens but puppet doesn't move**
→ Not a Python problem. Check the N-panel's Connect section shows
"Receiving" (not "Waiting"). If stuck on Waiting, the firewall is eating
UDP on port 11111. On macOS: System Settings → Network → Firewall → allow.

**`cv2` or `mediapipe` not found error in Terminal**
→ Step 4 didn't finish. Re-run the pip install command.

**Camera green light never comes on**
→ macOS needs camera permission for Terminal. System Settings → Privacy &
Security → Camera → enable Terminal. Close and reopen Terminal afterward.

**Webcam used by another app (Zoom, FaceTime, Teams)**
→ Quit the other app. Only one program can use the camera at a time.

---

## What this gives you long-term

Once `~/.ppparty/venv/` exists on a machine, it's permanent. You don't redo this
per-session. Future Blender updates, future addon zips, future macOS updates —
all fine. The only reason to redo this is if you reinstall the OS or manually
delete the `.ppparty` folder.

Same exact steps work on David's iMac, the laptop, any classroom machine, any
e-waste laptop you're prepping for CACHE. One-time setup per computer.
