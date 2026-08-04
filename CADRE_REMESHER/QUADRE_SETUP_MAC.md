# QUADRE — Mac Setup Guide

## The Problem
macOS blocks QUADRE's remeshing engine on first install because the files aren't signed by Apple. You'll get an error when you press "Clean Up My Shape" for the first time.

This only affects Macs. Windows machines work without this step.

## The Fix (30 seconds, one time per machine)

### Option A: Terminal Command (Recommended for Lab Setup)
1. Open **Terminal** (Applications → Utilities → Terminal)
2. Paste this command and press Enter:

```
xattr -r -d com.apple.quarantine ~/Library/Application\ Support/Blender/*/extensions/*/quadre/
```

3. If Blender is installed somewhere else, or you installed QUADRE manually, point to wherever the `quadre` addon folder lives:

```
xattr -r -d com.apple.quarantine /path/to/quadre/
```

4. Restart Blender. Done — you won't need to do this again on this machine.

### Option B: System Settings (If You Don't Have Terminal Access)
1. Open Blender and try to run "Clean Up My Shape" — it will fail
2. Open **System Settings → Privacy & Security**
3. Scroll down — you'll see a message about `liblib_quadwild.dylib` being blocked
4. Click **"Allow Anyway"**
5. Go back to Blender and try again — it will fail one more time
6. Repeat steps 2-4 for `liblib_quadpatches.dylib`
7. Run "Clean Up My Shape" again — it should work now

## For Lab Admins Setting Up Multiple Machines
If you're deploying QUADRE across a lab, run this on each Mac during setup:

```bash
# Clear quarantine for all users' Blender addon folders
sudo find /Users/*/Library/Application\ Support/Blender/*/extensions/*/quadre/ -exec xattr -d com.apple.quarantine {} + 2>/dev/null
```

Or if you're distributing QUADRE as a zip, clear the quarantine on the zip itself BEFORE students install it:

```bash
xattr -d com.apple.quarantine quadre-v0.3.0.zip
```

This way the extracted files won't be quarantined in the first place.

## Why This Happens
macOS Gatekeeper flags any software not signed with an Apple Developer certificate. QUADRE uses open-source remeshing libraries (QuadWild) that aren't signed. A future version will include proper code signing so this step goes away.

## Need Help?
Ask your CADRE Lab contact or email David Bayus.
