# Green Room Router Setup — Step by Step

## What You Need in Front of You
- Your MacBook Pro
- Your iPhone
- The Slate AX router (out of the box)
- The USB-C cable that came with the router
- A power source (your laptop's USB-C port, a wall charger, or a battery pack)

---

## STEP 1: Power On the Router

1. Plug the USB-C cable into the router
2. Plug the other end into your MacBook's USB-C port (or a wall charger)
3. Wait about 30 seconds — the lights on the front will blink and then settle
4. When the **WiFi light stays solid**, it's ready

---

## STEP 2: Find the Router's WiFi Name and Password

1. Flip the router over — look at the **sticker on the bottom**
2. You'll see something like:
   - **WiFi Name (SSID):** `GL-AXT1800-xxx`
   - **WiFi Password:** `goodlife` (or similar)
   - **Admin URL:** `192.168.8.1`
3. **Write these down or take a photo** — you'll need them for both devices

---

## STEP 3: Connect Your MacBook to the Router

1. Click the **WiFi icon** in your Mac's menu bar (top right)
2. Find the router's WiFi name (the `GL-AXT1800-xxx` from the sticker)
3. Click it, enter the password from the sticker
4. **YOU WILL SEE A WARNING** — it'll say something like "No Internet Connection"
5. **This is normal. Ignore it.** You don't need internet. Just dismiss it.
6. Now do this important extra step:
   - Open **System Settings** (Apple menu > System Settings)
   - Click **Wi-Fi** in the sidebar
   - Find the router's network in the list
   - Click the little **(i)** button next to it
   - Find **"Limit IP Address Tracking"** and turn it **OFF**
   - Close System Settings

---

## STEP 4: Connect Your iPhone to the Router

1. Open **Settings** on your iPhone
2. Tap **Wi-Fi**
3. Find the same router WiFi name (`GL-AXT1800-xxx`)
4. Tap it, enter the same password from the sticker
5. **YOU WILL SEE A WARNING** — it'll say "This network has no internet"
6. **Tap "Use Without Internet"** or **"Stay Connected"**
   - **CRITICAL:** If you don't do this, your iPhone will silently disconnect and switch back to cellular. The puppet will stop working and you won't know why.
7. Same extra step as the Mac:
   - Tap the **(i)** next to the router's network name
   - Turn **OFF** "Limit IP Address Tracking"

---

## STEP 5: Open Blender and Start Green Room

1. Open **Blender** on your MacBook
2. Make sure the Green Room addon is enabled
3. Load a puppet (or use whatever test file you already have open)
4. In the **N-Panel** (press N if it's not visible), find the **Green Room** tab
5. Click **"Connect My Phone"**
6. You'll see a message like: **"Listening on 192.168.8.xxx:11111"**
7. **Write down that IP address** (the `192.168.8.xxx` part) — you need it for the next step

---

## STEP 6: Set Up Live Link Face on Your iPhone

1. Open the **Live Link Face** app on your iPhone
2. Tap the **gear icon** (settings) in the top left
3. Under **"Target"**, you need to enter the IP from Step 5:
   - Tap on the target/IP field
   - Type in the IP address exactly as shown in Green Room (e.g. `192.168.8.123`)
   - The port should be **11111** (this is usually already set, but double check)
4. Go back to the main screen of Live Link Face
5. Tap **"Live"** to start streaming

---

## STEP 7: Check That It Works

1. Look at your MacBook screen — the puppet should be moving with your face
2. Try these:
   - Open your mouth — puppet's mouth should open
   - Blink — puppet should blink
   - Turn your head — puppet's head should turn
   - Smile — puppet should smile
3. If the puppet is moving: **you're done. It works.**

---

## Troubleshooting (If the Puppet Doesn't Move)

### "I don't see the router's WiFi on my Mac/iPhone"
- Is the router plugged in? Check that the lights are on.
- Wait 30 more seconds — it takes a moment to boot up.

### "The puppet isn't moving at all"
- Is your iPhone still connected to the router's WiFi? Check Settings > Wi-Fi.
  iPhones love to silently switch back to cellular. Reconnect and tap "Use Without Internet" again.
- Did you type the IP address correctly in Live Link Face? Double check — one wrong number and it won't connect.
- Is Live Link Face actually streaming? The app should show "Live" with a green dot.

### "The puppet moves but it's choppy/laggy"
- Make sure both devices are on the **5GHz** band (the router broadcasts both 2.4GHz and 5GHz — use the 5GHz one if you see two networks).
- Move the phone closer to the router.

### "My Mac keeps trying to switch to a different WiFi"
- Click the WiFi icon > click the (i) next to the router's network > turn on **"Auto-Join"**
- Forget any other nearby networks temporarily if your Mac keeps jumping.

### "Live Link Face says the port is in use"
- Go back to Blender, click **"Disconnect"** in the Green Room panel, wait a second, then click **"Connect My Phone"** again.

---

## Packing List for Saturday

- [ ] MacBook Pro + charger
- [ ] iPhone
- [ ] Slate AX router (the little black box)
- [ ] USB-C cable for the router
- [ ] Power source for router (battery pack or just use MacBook USB-C port)
- [ ] Know the router's WiFi name + password (photo of the sticker is fine)
- [ ] This guide on your phone, just in case
