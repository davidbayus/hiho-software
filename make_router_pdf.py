#!/usr/bin/env python3
"""Generate the Router Setup Guide PDF — clean, bold, zine-like."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ── Colors ──────────────────────────────────────────────
BLACK = HexColor("#1a1a1a")
DARK_GRAY = HexColor("#333333")
MID_GRAY = HexColor("#666666")
LIGHT_GRAY = HexColor("#e8e8e8")
WARN_BG = HexColor("#fff3cd")
WARN_BORDER = HexColor("#e6b800")
CRIT_BG = HexColor("#ffe0e0")
CRIT_BORDER = HexColor("#cc0000")
TIP_BG = HexColor("#e8f5e9")
TIP_BORDER = HexColor("#388e3c")
ACCENT = HexColor("#222222")

W, H = letter
MARGIN = 0.75 * inch

doc = SimpleDocTemplate(
    "/Users/davidbayus/Desktop/DOCTORATE/CLAUDE_ADMIN/THESIS_RESERACH/LOCAL_SOFTWARE/ROUTER_SETUP_GUIDE.pdf",
    pagesize=letter,
    leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=MARGIN, bottomMargin=MARGIN,
)

# ── Styles ──────────────────────────────────────────────
title_style = ParagraphStyle(
    "Title", fontName="Helvetica-Bold", fontSize=28,
    leading=34, textColor=BLACK, alignment=TA_LEFT,
    spaceAfter=6,
)
subtitle_style = ParagraphStyle(
    "Subtitle", fontName="Helvetica", fontSize=13,
    leading=18, textColor=MID_GRAY, alignment=TA_LEFT,
    spaceAfter=24,
)
step_num_style = ParagraphStyle(
    "StepNum", fontName="Helvetica-Bold", fontSize=48,
    leading=52, textColor=BLACK, alignment=TA_CENTER,
)
step_title_style = ParagraphStyle(
    "StepTitle", fontName="Helvetica-Bold", fontSize=18,
    leading=24, textColor=BLACK, alignment=TA_LEFT,
    spaceBefore=0, spaceAfter=10,
)
body_style = ParagraphStyle(
    "Body", fontName="Helvetica", fontSize=12,
    leading=18, textColor=DARK_GRAY, alignment=TA_LEFT,
    spaceAfter=6,
)
bullet_style = ParagraphStyle(
    "Bullet", fontName="Helvetica", fontSize=12,
    leading=18, textColor=DARK_GRAY, alignment=TA_LEFT,
    leftIndent=20, spaceAfter=4,
)
callout_style = ParagraphStyle(
    "Callout", fontName="Helvetica-Bold", fontSize=11,
    leading=16, textColor=DARK_GRAY, alignment=TA_LEFT,
)
callout_body_style = ParagraphStyle(
    "CalloutBody", fontName="Helvetica", fontSize=11,
    leading=16, textColor=DARK_GRAY, alignment=TA_LEFT,
)
section_head_style = ParagraphStyle(
    "SectionHead", fontName="Helvetica-Bold", fontSize=16,
    leading=22, textColor=BLACK, alignment=TA_LEFT,
    spaceBefore=20, spaceAfter=10,
)
mono_style = ParagraphStyle(
    "Mono", fontName="Courier-Bold", fontSize=13,
    leading=18, textColor=BLACK, alignment=TA_LEFT,
)
check_style = ParagraphStyle(
    "Check", fontName="Helvetica", fontSize=12,
    leading=20, textColor=DARK_GRAY, alignment=TA_LEFT,
    leftIndent=20, spaceAfter=4,
)

# ── Helpers ─────────────────────────────────────────────
usable_w = W - 2 * MARGIN

def callout_box(text, bg=WARN_BG, border=WARN_BORDER, label="HEADS UP"):
    """Warning / critical / tip callout."""
    inner = Paragraph(
        f'<b>{label}:</b>  {text}', callout_body_style
    )
    t = Table([[inner]], colWidths=[usable_w - 24])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 2, border),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    return t

def step_header(num, title):
    """Big number + title row."""
    num_p = Paragraph(f"{num}", step_num_style)
    title_p = Paragraph(title, step_title_style)
    t = Table(
        [[num_p, title_p]],
        colWidths=[0.9 * inch, usable_w - 0.9 * inch],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("LEFTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t

def hr():
    return HRFlowable(
        width="100%", thickness=1, color=LIGHT_GRAY,
        spaceBefore=16, spaceAfter=16,
    )

def thick_hr():
    return HRFlowable(
        width="100%", thickness=3, color=BLACK,
        spaceBefore=12, spaceAfter=12,
    )

def b(text):
    """Bulleted line."""
    return Paragraph(f"&bull;  {text}", bullet_style)

def numbered(n, text):
    return Paragraph(f"<b>{n}.</b>  {text}", bullet_style)


# ── Build the story ─────────────────────────────────────
story = []

# ── COVER / TITLE ───────────────────────────────────────
story.append(Spacer(1, 1.2 * inch))
story.append(Paragraph("GREEN ROOM", title_style))
story.append(Paragraph("Router Setup Guide", ParagraphStyle(
    "TitleSub", fontName="Helvetica", fontSize=22,
    leading=28, textColor=DARK_GRAY, spaceAfter=8,
)))
story.append(thick_hr())
story.append(Paragraph(
    "Everything you need to connect your phone to Green Room<br/>"
    "using the travel router. No internet required.",
    subtitle_style
))
story.append(Spacer(1, 0.4 * inch))

story.append(Paragraph("WHAT YOU NEED IN FRONT OF YOU", section_head_style))
story.append(b("Your MacBook Pro"))
story.append(b("Your iPhone"))
story.append(b("The Slate AX router (the little black box)"))
story.append(b("The USB-C cable that came with the router"))
story.append(b("A power source (laptop USB-C port, wall charger, or battery pack)"))
story.append(Spacer(1, 0.3 * inch))
story.append(callout_box(
    "You do NOT need internet for any of this. "
    "The router creates its own private WiFi network just for your devices.",
    TIP_BG, TIP_BORDER, "GOOD NEWS"
))

story.append(PageBreak())

# ── STEP 1 ──────────────────────────────────────────────
story.append(step_header(1, "POWER ON THE ROUTER"))
story.append(hr())
story.append(numbered(1, "Plug the USB-C cable into the router"))
story.append(numbered(2, "Plug the other end into your MacBook's USB-C port (or a wall charger)"))
story.append(numbered(3, "Wait about <b>30 seconds</b> \u2014 the lights will blink then settle"))
story.append(numbered(4, 'When the <b>WiFi light stays solid</b>, it\'s ready'))
story.append(Spacer(1, 0.4 * inch))

# ── STEP 2 ──────────────────────────────────────────────
story.append(step_header(2, "FIND THE WIFI NAME + PASSWORD"))
story.append(hr())
story.append(numbered(1, "Flip the router over \u2014 look at the <b>sticker on the bottom</b>"))
story.append(Paragraph("You'll see something like:", body_style))
story.append(Spacer(1, 6))

info_data = [
    [Paragraph("<b>WiFi Name:</b>", body_style),
     Paragraph('<font name="Courier-Bold">GL-AXT1800-xxx</font>', body_style)],
    [Paragraph("<b>Password:</b>", body_style),
     Paragraph('<font name="Courier-Bold">goodlife</font>  (or similar)', body_style)],
]
info_table = Table(info_data, colWidths=[1.6 * inch, usable_w - 1.6 * inch])
info_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 12),
]))
story.append(info_table)
story.append(Spacer(1, 8))
story.append(callout_box(
    "Take a photo of the sticker \u2014 you'll need the name and password for both devices.",
    TIP_BG, TIP_BORDER, "TIP"
))
story.append(Spacer(1, 0.4 * inch))

# ── STEP 3 ──────────────────────────────────────────────
story.append(step_header(3, "CONNECT YOUR MACBOOK"))
story.append(hr())
story.append(numbered(1, "Click the <b>WiFi icon</b> in your menu bar (top right)"))
story.append(numbered(2, 'Find the router\'s WiFi name (<font name="Courier-Bold">GL-AXT1800-xxx</font>)'))
story.append(numbered(3, "Click it \u2014 enter the password from the sticker"))
story.append(Spacer(1, 8))
story.append(callout_box(
    'Your Mac will say <b>"No Internet Connection"</b> \u2014 '
    "this is normal! You don't need internet. Just dismiss the warning.",
    WARN_BG, WARN_BORDER, "HEADS UP"
))
story.append(Spacer(1, 10))
story.append(Paragraph("Then do this important extra step:", body_style))
story.append(numbered(4, "Open <b>System Settings</b> (Apple menu \u2192 System Settings)"))
story.append(numbered(5, "Click <b>Wi-Fi</b> in the sidebar"))
story.append(numbered(6, "Find the router's network \u2014 click the little <b>(i)</b> button next to it"))
story.append(numbered(7, 'Find <b>"Limit IP Address Tracking"</b> and turn it <b>OFF</b>'))

story.append(PageBreak())

# ── STEP 4 ──────────────────────────────────────────────
story.append(step_header(4, "CONNECT YOUR IPHONE"))
story.append(hr())
story.append(numbered(1, "Open <b>Settings</b> on your iPhone"))
story.append(numbered(2, "Tap <b>Wi-Fi</b>"))
story.append(numbered(3, 'Find the same router WiFi name (<font name="Courier-Bold">GL-AXT1800-xxx</font>)'))
story.append(numbered(4, "Tap it \u2014 enter the same password from the sticker"))
story.append(Spacer(1, 8))
story.append(callout_box(
    'Your iPhone will say <b>"This network has no internet."</b><br/>'
    'Tap <b>"Use Without Internet"</b> or <b>"Stay Connected."</b>',
    WARN_BG, WARN_BORDER, "HEADS UP"
))
story.append(Spacer(1, 8))
story.append(callout_box(
    "If you skip this step, your iPhone will <b>silently switch back to cellular</b>. "
    "The puppet will stop moving and you won't know why. "
    "This is the #1 gotcha.",
    CRIT_BG, CRIT_BORDER, "CRITICAL"
))
story.append(Spacer(1, 10))
story.append(Paragraph("Same extra step as the Mac:", body_style))
story.append(numbered(5, "Tap the <b>(i)</b> next to the router's network name"))
story.append(numbered(6, 'Turn <b>OFF</b> "Limit IP Address Tracking"'))

story.append(Spacer(1, 0.5 * inch))

# ── STEP 5 ──────────────────────────────────────────────
story.append(step_header(5, "OPEN BLENDER + GREEN ROOM"))
story.append(hr())
story.append(numbered(1, "Open <b>Blender</b> on your MacBook"))
story.append(numbered(2, "Load a puppet (or use your test file)"))
story.append(numbered(3, 'Press <b>N</b> to open the side panel \u2014 find the <b>"Green Room"</b> tab'))
story.append(numbered(4, 'Click <b>"Connect My Phone"</b>'))
story.append(numbered(5, 'You\'ll see: <font name="Courier-Bold">Listening on 192.168.8.xxx:11111</font>'))
story.append(Spacer(1, 8))
story.append(callout_box(
    "Write down that IP address (the <b>192.168.8.xxx</b> part) \u2014 you need it for the next step.",
    TIP_BG, TIP_BORDER, "WRITE THIS DOWN"
))

story.append(PageBreak())

# ── STEP 6 ──────────────────────────────────────────────
story.append(step_header(6, "SET UP LIVE LINK FACE"))
story.append(hr())
story.append(numbered(1, "Open the <b>Live Link Face</b> app on your iPhone"))
story.append(numbered(2, "Tap the <b>gear icon</b> (settings) in the top left"))
story.append(numbered(3, 'Under <b>"Target"</b>, enter the IP address from Step 5'))
story.append(numbered(4, 'Make sure the port is <b>11111</b>'))
story.append(numbered(5, "Go back to the main screen"))
story.append(numbered(6, 'Tap <b>"Live"</b> to start streaming'))

story.append(Spacer(1, 0.5 * inch))

# ── STEP 7 ──────────────────────────────────────────────
story.append(step_header(7, "CHECK THAT IT WORKS"))
story.append(hr())
story.append(Paragraph(
    "Look at your MacBook. The puppet should be moving with your face.",
    body_style
))
story.append(Spacer(1, 8))
story.append(b("Open your mouth \u2192 puppet's mouth opens"))
story.append(b("Blink \u2192 puppet blinks"))
story.append(b("Turn your head \u2192 puppet's head turns"))
story.append(b("Smile \u2192 puppet smiles"))
story.append(Spacer(1, 14))
story.append(callout_box(
    "If the puppet is moving with your face \u2014 <b>you're done. It works.</b>",
    TIP_BG, TIP_BORDER, "SUCCESS"
))

story.append(PageBreak())

# ── TROUBLESHOOTING ─────────────────────────────────────
story.append(Paragraph("TROUBLESHOOTING", title_style))
story.append(thick_hr())
story.append(Spacer(1, 8))

story.append(Paragraph('"I don\'t see the router\'s WiFi"', step_title_style))
story.append(b("Is the router plugged in? Check that the lights are on."))
story.append(b("Wait 30 more seconds \u2014 it takes a moment to boot up."))
story.append(Spacer(1, 16))

story.append(Paragraph('"The puppet isn\'t moving at all"', step_title_style))
story.append(b("Is your iPhone still on the router's WiFi? Check Settings \u2192 Wi-Fi. "
               "iPhones love to silently switch back to cellular."))
story.append(b("Did you type the IP address correctly in Live Link Face? "
               "One wrong number and it won't connect."))
story.append(b('Is Live Link Face streaming? It should show "Live" with a green dot.'))
story.append(Spacer(1, 16))

story.append(Paragraph('"The puppet moves but it\'s choppy"', step_title_style))
story.append(b("Use the <b>5GHz</b> band if the router broadcasts two networks (2.4 and 5)."))
story.append(b("Move the phone closer to the router."))
story.append(Spacer(1, 16))

story.append(Paragraph('"My Mac keeps switching to a different WiFi"', step_title_style))
story.append(b('Click WiFi icon \u2192 (i) next to the router\'s network \u2192 turn on <b>"Auto-Join"</b>.'))
story.append(b("Forget other nearby networks temporarily if your Mac keeps jumping."))
story.append(Spacer(1, 16))

story.append(Paragraph('"Live Link Face says the port is in use"', step_title_style))
story.append(b('In Blender, click <b>"Disconnect"</b> in the Green Room panel, '
               'wait a second, then click <b>"Connect My Phone"</b> again.'))

story.append(PageBreak())

# ── PACKING LIST ────────────────────────────────────────
story.append(Paragraph("PACKING LIST FOR SATURDAY", title_style))
story.append(thick_hr())
story.append(Spacer(1, 12))
story.append(Paragraph("CADRE 40th Celebration \u2014 April 12, 2026", subtitle_style))

items = [
    "MacBook Pro + charger",
    "iPhone",
    "Slate AX router (the little black box)",
    "USB-C cable for the router",
    "Power source for router (battery pack or MacBook USB-C port)",
    "Router WiFi name + password (photo of the sticker)",
    "This guide on your phone, just in case",
]
for item in items:
    story.append(Paragraph(f"\u25a1  {item}", check_style))

story.append(Spacer(1, 0.5 * inch))
story.append(hr())
story.append(Paragraph(
    "Green Room \u2014 CADRE Lab, SJSU",
    ParagraphStyle("Footer", fontName="Helvetica", fontSize=10,
                   textColor=MID_GRAY, alignment=TA_CENTER),
))

# ── Build ───────────────────────────────────────────────
doc.build(story)
print("PDF saved to ROUTER_SETUP_GUIDE.pdf")
