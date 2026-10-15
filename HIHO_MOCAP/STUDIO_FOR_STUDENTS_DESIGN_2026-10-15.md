# Studio for students: the auto-rig and bind workflow for ART 175 (design)

*2026-10-15, laptop (`Davids-MacBook-Pro`, checked). Design only, no code changed, no build made. This is the next step
named in `AUTORIG_STATE_OF_THE_ART_2026-10-15.md` section 5. It turns that doc's direction (section 4) into a panel a
student can follow, with the blockout-rig door from `APOSE_REST_DESIGN_2026-10-15.md` section 5 and the gap list from
`ACTIONFORGE_STUDY_2026-10-13.md` section 5. David decides everything in section 9 before any build; the three open
decisions he already owns (study only or reuse GPL code; fingers on the auto-rig; the Easy Rigify seat) are written
around, with both options where they change the design.*

**Read first:** `AUTORIG_STATE_OF_THE_ART_2026-10-15.md` (section 4 is the direction), `APOSE_REST_DESIGN_2026-10-15.md`
(section 5, the blockout door), `ACTIONFORGE_STUDY_2026-10-13.md` (section 5), `STUDIO_SECTION_DESIGN_2026-07-01.md` and
`DEV_LOG_STUDIO_SECTION_JULY2026.md` (what exists and how it was tested), then the live code: `panel/studio_panel.py`,
`operators/markers.py`, `operators/autorig.py`, `core/marker_fit.py`, `core/voxel_skinning.py`,
`operators/send_to_character.py`, `core/rotation_retarget.py`.

**Who this is for:** the ART 175-02 students (Spring 2027, Wednesdays 12 to 2:50 in Art 141, about 24 people, ART 102
prerequisite). They can model in Blender. They have never rigged. Most will bring an unrigged character made in ART 102,
often several loose pieces (floating head, separate hands, a hat). Some will model the class "dummy body" instead.
Nothing in this doc assumes a student knows what a weight, a bone roll or a constraint is.

---

## 0. The short version

Today the Studio section works end to end (David's chibi, July), but it reads like a tool for David: Import Character,
Add Markers, Mirror, Skinning mode, Auto-Rig, Send to Character, and a student has to know that Auto-Rig both fits and
skins in one go, with no way to look before the weights land. Auto-Rig Pro's Smart workflow is the same engine family
with a better sequence: normalize quietly, few mirrored markers with a guess, a look at the skeleton before binding, one
Bind button with named fix-ups.

After this design the Studio section reads top to bottom in five HIHO steps:

1. **Bring in your character**
2. **Where are the joints?**
3. **Preview the skeleton**
4. **Bind**
5. **Put the motion on it**

Two doors lead into step 4. **Door A**, the marker auto-rig: the student points at the joints, HIHO builds a skeleton to
fit. **Door B**, the blockout rig: the student models their character *around* a shipped HIHO rig at rest and skips the
joints entirely. Both doors end at the same Bind button and the same Send to Character, because both rigs carry the
mocap rig's bone names. The engine does not change: the fixed skeleton fitted to markers, the vendored MIT voxel solver,
Blender's Automatic Weights as the fallback. The work is the sequence, the words, the refusals, and three additions:
finger tips found from the hand's outline, a Guess button that uses HIHO's own tracker on two renders of the character,
and a shipped A-pose rig file.

---

## 1. What exists today (1.5.8), in one table

| Studio panel today | Code | What it does | Known limits |
|---|---|---|---|
| 1. Choose Take: Load Take, path box | `operators/load_take.py` | Folder picker to any processed take; spawns the empties and the mocap rig; sets the scene clock | The path box under the button reads as an input but is an output (backlog) |
| 2. Preview: Play | Blender's own play | Plays the loaded take | |
| 3. Character: Import Character | `operators/import_character.py` | `.fbx` / `.obj` picker; lands the file in its own `HIHO_Character_<name>` collection; reports piece and vertex counts; warns if the file carries an armature | Does not center, face, or apply transforms (a July call, see 2.1) |
| Add Markers | `operators/markers.py` | 13 named sphere empties at classic human fractions of the character's height; identity in a custom property, so renaming is safe; re-run resets them | All 13 shown; the student drags both sides |
| Mirror axis, Left to Right, Right to Left | same file | Copies one side's markers across the character's middle | A button, not a mode |
| Skinning: Voxel / Automatic | `properties.py` | Which weight engine Auto-Rig uses | The student has to know what these words mean |
| Auto-Rig | `operators/autorig.py`, `core/marker_fit.py`, `core/voxel_skinning.py` | Pushes every marker to the middle of the body's depth; builds the 23 body bones (mocap names, rolls read from the rest-pose table, A or T per the preference); neck and skull from the silhouette pinch; skins with the voxel solver, falls back to Automatic Weights; re-run replaces the old rig cleanly | Fit and skin in one click; no fingers (no markers drive them); no look before the weights |
| Character target picker, Send to Character | `operators/send_to_character.py`, `core/rotation_retarget.py` | Scales the loaded take to the character's hip height; copies each bone's world rotation from the mocap rig, and the pelvis location; skips bones the character does not have and says how many fingers were skipped | Needs a take loaded and a rig picked (the button is grey otherwise) |
| Diagnostics: Map the Volume, Spawn Empties | | Capture inspection tools | Not a student step |

Bake Animation and Save Out live in the main panel as step 6 and work on any selected rig; Save Out refuses a rig that
still has live constraints and says "press Bake Animation first".

The whole pipeline ran on David's chibi on 2026-07-01 (build 1.4.8 onward) and his verdict on 1.4.11 was "much
improved". **No student has ever run it.** That is the real gap, and section 8 puts a test with real student characters
before every build.

---

## 2. The five steps, in HIHO words

Every button below has three parts: what it does when it works, what it refuses and the sentence it says, and what the
status line at the top of the panel reads afterwards. The hover text on each button is the "does" line in one sentence.
Refusals are plain sentences that name the fix, never a code word. Nothing in Studio touches the network; the panel
says so once, in small text under the section title: *"Everything here runs on this computer. Nothing is uploaded."*
(ActionForge gap 7: the top comment under that video was this worry.)

### 2.1 Step 1. Bring in your character

| Button or box | Does | Refuses, and says |
|---|---|---|
| **Bring in a file** (picker, `.fbx` `.obj` `.glb`) | Imports the file into its own `HIHO_Character_<name>` collection, then normalizes it (below). Selects it. | Wrong file type: "Pick a .fbx, .obj or .glb file." File missing or unreadable: "Could not read that file." File imports nothing: "The file had no character in it." |
| **Use what is selected** | Takes the selected mesh pieces already in the scene (the student modeled in this file, or appended a blockout) as the character and normalizes them. Puts them in a `HIHO_Character_<name>` collection named after the active object. | Nothing selected or no meshes: "Select your character's pieces first (click one, shift-click the rest)." |
| **Turn** (four small arrows: face me, turn left, turn right, turn around) | Rotates the whole character a quarter turn at a time until it faces the front view (Blender's minus Y). Shown only when the facing guess is unsure. | |

**Normalize silently (new, the ARP lesson).** After either button, HIHO: joins nothing and renames nothing; applies
location, rotation and scale on every piece (so the markers and the solver see the real shape); moves the whole character
so its feet touch the floor (lowest point at height zero) and its middle sits on the origin; checks which way it faces
(the toe test already in `marker_fit.detect_forward`, falling back to the Turn arrows when unsure); and checks the scene
units are plain meters at scale 1.0.

July's design said "do not auto-apply transforms, students may have intentional setups". That was right for a file a
student is still working on. It is wrong for the rigging step, where every tool in the field (ARP, Easy Rigify,
ActionForge, Mixamo) normalizes before fitting, and an unapplied scale is item one on the messy-mesh list that breaks
every auto-rigger. Proposal: normalize the pieces HIHO just imported without asking, and for "Use what is selected" say
in the status line what was done ("Applied scale and rotation on 3 pieces, set the feet on the floor") so nothing is
hidden. The Undo stack covers regret. **David's call, question 4.**

**Size check.** If the character stands under 0.3 m or over 4 m, the status line says so and offers one button: **Make
it 1.7 m tall** (uniform scale, applied). The marker fit itself does not care about size, but Automatic Weights fails
on tiny characters and the shipped blockout rig is in real meters, so a sane size early saves two later surprises.

**What it refuses, beyond the table.** A character that already wears a rig from another tool (Mixamo, Rigify, ARP):
"This character is already rigged to <name>. HIHO rigs one skeleton at a time. Remove that rig, or bring in the
unrigged model." (Today's Auto-Rig does this check late; it moves here so the student hears it first. The ActionForge
"keeps its own skeleton" door for Mixamo-rigged characters is a separate design, gap 2, not in this doc.)

**Status line after:** "Your character is in: 8 pieces, 24,310 points, 1.72 m tall, facing front. Next: where are the
joints?"

### 2.2 Step 2. Where are the joints?

The student answers one question: where are the joints on this character. Two ways to answer, and both end with the
same markers in the scene.

| Button or box | Does | Refuses, and says |
|---|---|---|
| **Guess** | Renders the character from the front and from the side, runs HIHO's own 2D body tracker on the two pictures, and places the markers where it found the joints (section 5). Markers it was unsure about stay on the template and are named in the status line. | No character: "Bring in your character first." The processing setup is not installed on this computer: "Guess needs the HIHO processing setup. Place the markers by hand instead." (The button stays visible so a student knows it exists.) |
| **Place by hand** (today's Add Markers) | Puts the markers near the right places using classic human proportions, ready to drag. Re-pressing resets them. | No character: "Bring in your character first." Character has no height: "This mesh is empty." |
| **Mirrored** (checkbox, on by default) | While on, only the left side's markers plus the three middle ones are shown (seven in all: head, left shoulder, elbow, wrist, hip, knee, ankle); the right side follows across the character's middle, live. Turn it off for a lopsided character and all 13 appear. | |
| **Left to Right, Right to Left** | Kept for the unmirrored case: copies one side to the other once. | No markers: "Place the markers first." |
| **Fingers** (optional line, folded by default): count box (5, 4, or 0 = mitten), **Find fingertips** | Finds each hand's fingertips from the mesh outline and marks them (section 4). | No wrist markers yet: "Place the wrist markers first." Fewer tips found than the count: builds what it found and says "Found 3 of 5 fingertips on the left hand. Spread the fingers apart, palms down, and try again." |

**Counter, always visible:** "7 of 7 placed" (mirrored) or "13 of 13 placed". A marker counts as placed once it has
moved off the template, or once Guess placed it with confidence. The count is the student's checklist, so Preview can
refuse by name when one is missing.

**Which markers.** The 13 HIHO markers stay (head, shoulders, elbows, wrists, hips, knees, ankles). ARP uses six and
scans the mesh for elbows and knees; HIHO asks for elbows and knees because student characters bend in odd places (a
chibi's knee is not at 28 percent of its height) and a marker is cheaper to drag than a scan is to debug. The mirrored
mode cuts the dragging to seven, which is close to ARP's six.

**Depth.** Students place markers in the front view, so every marker sits at one flat depth. Today's depth centering
(push each marker to the middle of the body along the front-to-back line, done inside Auto-Rig) moves to the moment the
student lets go of a marker, so the marker visibly snaps into the body. Same code, earlier, visible.

**Status line after:** "7 of 7 placed. Next: preview the skeleton."

### 2.3 Step 3. Preview the skeleton

Today the fit and the weights happen in one click. Splitting them is the single biggest change for a learner: the
skeleton appears inside the character, the student looks from the front and the side, nudges a marker, previews again.
No weights yet, so nothing can go wrong with the mesh, and previewing is fast (the fit is pure geometry).

| Button | Does | Refuses, and says |
|---|---|---|
| **Preview the skeleton** | Builds the HIHO skeleton fitted to the markers (today's fit half: 23 body bones, mocap names, rest-pose rolls, neck and skull from the silhouette pinch, plus the finger chains if fingertips were found). Draws it in front of the mesh. Re-pressing replaces the previous preview. Nothing is bound. | A marker is missing: "Place the Left Knee marker first (1 of 7 missing)." Plain names, from the marker labels, never `knee.L`. No character: "Bring in your character first." |
| **Hide / Show markers** | Toggles the marker spheres so the skeleton can be read. | |

What the student checks, said in the hover text and in the handout: the bones run down the middle of each limb from the
front and from the side; the neck ends where the head starts; the feet point forward. If not, drag a marker and
preview again.

**Status line after:** "Skeleton fitted: 23 bones (or 63 with fingers). Look from the front and the side. Next: bind."

### 2.4 Step 4. Bind

One button. The engine is chosen for the student. The fix-ups are checkboxes with plain names (section 6).

| Button or box | Does | Refuses, and says |
|---|---|---|
| **Engine: Auto / Voxel / Automatic Weights** (Auto by default) | Auto picks Voxel when the character has more than one piece or any piece is not watertight, and Automatic Weights when it is one clean piece. The pick is shown in the status line so the student learns the rule. | |
| **Fix-ups** (checkboxes, section 6) | Named passes that run after the weights land. | |
| **Bind** | Attaches every piece to the previewed skeleton with weights from the chosen engine, runs the ticked fix-ups, and parents the pieces to the rig. If the voxel solver cannot run (binary missing, crash, timeout) it falls back to Automatic Weights and says so. Re-pressing re-binds from scratch (old weights removed first, today's purge). | No previewed skeleton: "Preview the skeleton first." A piece is bound to a foreign rig: as in step 1. Both engines failed: "Bind failed: <reason>. Try Automatic Weights, or check the character for loose points and inside-out faces." |
| **Test pose** | Plays a canned three-second wiggle on the rig (elbows bend, knees bend, head turns, spine twists a little) so the student sees the skin move before any take. Press again or Esc to stop; the rig returns to rest. Keyframes live on a throwaway action the button removes. | No bound rig: "Bind first." |

On Door B (section 3) the Bind button sees that the picked rig is the shipped blockout rig and skips the fit: the
pieces bind to that rig as it stands. Same button, same fix-ups.

**Status line after:** "Bound 8 pieces to 23 bones with the voxel solver (several pieces). Press Test pose, then put
the motion on it."

### 2.5 Step 5. Put the motion on it

Unchanged code, two buttons, the words moved so the order is obvious.

| Button or box | Does | Refuses, and says |
|---|---|---|
| **Load a take** (folder picker) | Brings a processed HIHO take into the scene: the empties, the mocap rig, the scene clock. The take plays on its own rig first, so the student sees the performance before it reaches their character. | Not a take: "That folder is not a processed HIHO take. Pick the folder that holds output_data." |
| **Character rig** (picker, filled in by Bind, still shown) | Which rig receives the motion. | |
| **Put the motion on it** (today's Send to Character) | Scales the take to the character's hip height, copies every bone's world rotation from the mocap rig and the pelvis position, so the character performs the take at its own proportions. Says how many bones were bound and how many were skipped. | No take loaded: "Load a take first." No rig picked: "Pick your character's rig." The button is grey until both are true (today's poll). |

After that the main panel's step 6 takes over: Bake Animation, Lock Feet if the feet slide, Save Out. Save Out already
refuses an unbaked rig in plain words.

**Status line after:** "Your character is performing the take. Press Spacebar. Bound 23 bones; 40 finger bones skipped
(this rig has no fingers)." On Door B the same line reads "Bound 63 bones" and the hands move.

---

## 3. The two doors

| | Door A: the marker auto-rig | Door B: model around the HIHO rig |
|---|---|---|
| Who | A student with a finished character (their ART 102 work, a downloaded model) | A student starting a character for this class, or building the class dummy body |
| Steps | 1, 2, 3, 4, 5 | 1 (Add the HIHO rig, then Use what is selected), 4, 5 |
| Skeleton | 23 body bones fitted to the markers, plus finger chains if fingertips were found and David says yes to fingers (section 9) | The full 63-bone mocap rig at A-pose rest, from the shipped file, scaled by the student if they like |
| Fingers | Only with the fingertip finder | For free: all 40 finger bones, same names as the mocap rig |
| What can go wrong | Markers off, odd proportions, loose pieces | The student models away from the rig (a hand not around the hand bones), or scales the rig unevenly |
| Bind | Same button; the fit runs first | Same button; the fit is skipped because the rig *is* the skeleton |
| Put the motion on it | Same button | Same button |

**How Door B appears in the panel.** Step 1 gets a third button, **Add the HIHO rig**: appends the shipped rig file
(section 3.1) into a `HIHO_Rig` collection, at the origin, feet on the floor, facing front, and selects it. The hover
text: "Build your character around these bones. Scale the whole rig to your size first if you want (press S, type a
number). When the character is done, select its pieces and the rig, and press Bind." A small line under the button:
"Keep every piece of the character close to a bone that should move it. A hand goes around the hand bones."

**What Bind does differently on Door B.** When the picked rig carries the shipped rig's tag (a custom property on the
armature, `hiho_rig_kind = blockout`, with the rig's version), Bind: refuses an uneven scale on the rig ("The rig is
scaled unevenly (X 1.2, Y 1.0, Z 1.4). Rigs scale all three the same; undo the scale and try again"); applies a uniform
object scale into the bones so the bone lengths are real; then binds the selected pieces to it with the chosen engine
and fix-ups, exactly as Door A. No markers are needed and no marker check runs. If markers exist in the scene from an
earlier try, they are ignored and the status line says so.

**Why Send to Character serves both doors unchanged.** It copies world rotations bone by bone, matched by name, plus the
pelvis position, and skips names the mocap rig does not have. The Door A rig uses the mocap rig's 23 body names. The
Door B rig *is* the mocap rig's skeleton (63 names, same rest pose, same parents). Proportions can differ from the
performer's, because rotations are copied and only the pelvis travels; that is the July rotation-retarget decision and it
holds for both doors. The hip-height scaling of the take also works for both, because both rigs have a `pelvis`.

**Which door the class leads with.** The ART 175 design doc gives every student two paths for assets: the dummy body
made in class, or their own content. The dummy body is Door B by construction (model the "grown chibi" around the shipped
rig, and every student can bind the same body in chunk 5). Their own content is Door A. Both doors ship; the handout
teaches Door B first because it cannot go wrong at the joints.

### 3.1 The shipped blockout rig asset

**File:** `assets/HIHO_Rig_Apose_v1.blend`, inside the addon zip (one new folder for `build_zip.py` to include). Inside:
one collection `HIHO_Rig_Apose`, one armature object `HIHO_Rig` with armature data `HIHO_Rig_data`, 63 bones, A-pose
rest, at the origin, feet on the floor at height zero, facing minus Y, object scale 1, no animation, no constraints, no
empties, no mesh, no custom shapes. The armature carries two custom properties: `hiho_rig_kind = blockout` and
`hiho_rig_source = 2026-09-19_16-06-36` (the take it was measured from), plus the addon version that made it. Size on
disk: well under a megabyte.

**Proportions: David's clean take `2026-09-19_16-06-36`** (BASEMENT, 2026-09-19, RTMPose, his "Come over here" gesture,
verdict "usable", the steadiest bone lengths in the take log at 5.07 percent wobble, and the take the 1.5.7 finger fix
left within 1 mm). David is 5 feet 8, so the rig stands about 1.73 m. The A-pose note records the pelvis figure as
1.42 m; that number is odd for a standing pelvis and must be re-measured on the spawned rig at build time, not copied.
Bone lengths are whatever 1.5.8's Spawn Rig measures on that take (median over frames, finger ceiling applied), so the
rig is the same skeleton a student will see when they load that take, which is the point: a character modeled around it
fits the motion it was measured from.

**Why his take and not a student's.** There is no student-performer take yet (S01 is reserved for the first one). A
child-proportioned rig is worth a second file once a student take exists, with the student's opt-in, and nothing in this
design changes for it: Bind reads the tag, not the proportions. **Question 5 for David.**

**Scale.** Real meters, one Blender unit per meter, like every HIHO take. A student who wants a 2.5 m giant or a 0.9 m
kid scales the whole rig uniformly before modeling; Bind applies it. Nothing in Send to Character cares, because it
copies rotations and scales the take to the pelvis height.

**How it is made with the addon, no hand editing.** A diagnostics script, `diagnostics/make_blockout_rig.py`, run once
by David through Blender's command line against the take folder:

1. Load the take and Spawn Rig with the A-pose preference (today's code).
2. Remove every constraint from the rig, clear its animation, delete the empties and the skelly root, reset the pose.
3. Move the rig so the lowest foot bone sits on the floor and the pelvis is over the origin; confirm it faces minus Y.
4. Tag the armature, rename it `HIHO_Rig`, put it in the `HIHO_Rig_Apose` collection alone.
5. Save as `assets/HIHO_Rig_Apose_v1.blend` with nothing else in the file.

The same script, pointed at a different take, makes the second rig later. The script is the recipe; the file is the
asset; the "Add the HIHO rig" button appends the file. A rest-pose change (T-pose preference) does not affect the shipped
file; it is A-pose by decision (`APOSE_REST_DESIGN` section 4c: starter clips and shared rigs want one rest pose for all
time).

**The dummy body.** The ART 175 design doc's open question 6 (what the dummy body is) has a lean: "a grown chibi, our
own HIHO version of a FreeMoCap Skelly". A grown chibi OBJ exists in the cold-storage pen
(`_COLD_STORAGE_2026-08-02/02_OLD_DESKTOP_SNAPSHOT_JUN27/.../GROWNUP_CHIBI/CHIBI_GROWN_LOWPOLY_UVSP.obj` and a
`CHIBI_GROWN_WALK.blend` beside it). If David pulls it out of the pen, it is the natural first Door B character: fit it
around the shipped rig, bind, and it becomes the class body. Claude does not touch the pen.

---

## 4. Fingers from the hand's outline (no finger markers)

Today's auto-rig has no finger bones, so a mocapped hand on a Door A character has nothing to drive, while the mocap
side now captures fingers cleanly (1.5.7). ARP's trick, in reverse: no finger markers; the five tips are the farthest
points of each hand's outline. The student only spreads the fingers of the model, palms down, which the handout and the
hover text say in those words.

**What the finder knows going in.** The wrist marker and the elbow marker give the forearm direction. The character faces
minus Y. The hand mesh is whatever lies past the wrist along the forearm direction, within a generous radius (a hand is
rarely longer than the forearm).

**How it finds the tips.**

1. Collect every vertex past the wrist along the forearm direction, from every piece (a detached hand piece is fine).
2. Find the farthest vertex from the wrist. That is the longest fingertip (usually the middle finger). Its distance sets
   the hand's size.
3. Project the collected vertices onto the palm plane (palms down means the plane is level, and the forearm direction
   lies in it). Sweep the angle around the wrist in that plane. In each angle slice keep the vertex farthest from the
   wrist. The outline is now a curve of distance against angle.
4. The tips are the peaks of that curve: a point farther from the wrist than its neighbors on both sides, at least a
   set share of the longest tip (so a knuckle bump does not count), and at least a set angle from the next peak (so one
   wide finger does not count twice). Take the strongest peaks up to the count the student set.
5. Name them by angle. For the right hand the thumb is the peak farthest toward the body's middle; for the left hand
   the mirror; then index, middle, ring, pinky in order across. With count 4 there is no pinky. With count 0 (mitten)
   nothing is built and the hand bone alone stays, as today.
6. Place a small marker sphere at each tip named in plain words ("Left Index Tip") so the student can drag one that
   landed wrong, same identity-by-property scheme as the 13 body markers.

**How the finger bones are built from the tips.** For each tip, a chain of four bones with the mocap rig's names and
parents: the metacarpal from the hand bone's head (the wrist) toward the tip, stopping at the knuckle, which is set at a
fixed share of the wrist-to-tip distance (about 45 percent for the fingers, the thumb's first bone shorter); then three
phalanges splitting the rest of the way to the tip in the mocap rig's proportions. Each bone's roll aligns to the rest
table, as the body bones do today. Knuckle depth is read off the mesh with the same ray test as the depth centering, so
the chain runs through the finger rather than over it. The result is 63 bones with the mocap rig's names, so Send to
Character binds the fingers with no new code and the "40 finger bones skipped" line disappears.

**What it refuses.** Fewer peaks than the count: builds what it found, keeps the rest skipped, and says which hand to
spread. No vertices past the wrist (a character with no hands, or wrist markers placed at the fingertips): "No hand found
past the Left Wrist marker. Move the marker to the wrist, where the hand begins." Hands that are one blob (mitten, boxing
glove): count 0 is the answer and the message says so after one try: "Found 1 of 5 fingertips on the right hand. If the
hand has no separate fingers, set Fingers to 0."

**Where it can go wrong, honestly.** Fingers modeled curled, fingers touching, a hand holding a prop, a thumb tucked
under. None of these are fixable by the finder; the handout says spread, flat, empty. The thresholds (share of the
longest tip, angle between peaks) are set during the build on two meshes: the Rigify human metarig's matching mesh (a
real hand, the bone reference rule) and the ART 102 chibi (`SJSU_ALL/ART102_FA26/DEMO_FILES/CHIBI_PAWRAPPA_TEST.obj`).

**If David says no to fingers on the auto-rig (section 9, question 2)**, this whole section waits, Door A stays at 23
bones, and the handout points finger-wanting students to Door B, where the 40 finger bones come free. The panel line
"Fingers" simply does not draw. Nothing else in this design depends on it.

---

## 5. Guess: markers from HIHO's own tracker on two renders

ARP's Guess Markers screenshots the model from the front, side and top and runs a 2D pose detector on each. HIHO already
ships two such detectors for live footage: MediaPipe in the 1.x processing setup and RTMPose in the 2.0 setup. Both are
trained on pictures of people, and a rendered character is a picture of a person. No new dependency; a new external
script and a render.

**What the button does.**

1. Renders the character twice at 1280 by 720, the size the trackers see from the cameras: once from the front
   (orthographic, looking down plus Y at the character's middle) and once from the character's left side. Solid grey
   material, flat lighting, plain background, Blender's Workbench engine so it takes a second and needs no lights. The
   renders go to a temporary folder and are deleted after.
2. Runs `external/guess_markers.py` in the installed processing setup (the 2.0 setup with RTMPose first; the 1.x setup
   with MediaPipe if that is the only one). The script is the same shape as `external/volume_map.py`: one entry point,
   plain-text markers on its output (`HIHO_INFO::`, `HIHO_GUESS::<json>`, `HIHO_ERROR::`), so the operator reads it the
   way Process and Map the Volume already read their scripts. No Blender imports in it.
3. Reads back, per picture, the 2D joints the trackers already name: nose, shoulders, elbows, wrists, hips, knees,
   ankles, each with a confidence.
4. Turns pixels into scene positions. The front render fixes each marker's sideways and up-down position (an
   orthographic camera makes that a straight scale from the render size to the character's height). The side render
   fixes the front-to-back position for the same joints. Where the side view is unsure (an arm hidden behind the body),
   the depth centering already in the code fills it in. The head marker comes from the nose, moved up the head's
   silhouette to the crown the way the marker template expects.
5. Places the 13 markers (or 7 with Mirrored on, averaging the two sides' guesses mirrored) and leaves any marker under
   the confidence floor on the template. The status line names them: "Guessed 11 of 13. Check the Left Elbow and Right
   Elbow by hand."

**What it refuses.** No character: "Bring in your character first." No processing setup on this machine (neither
preference points at a working Python): "Guess needs the HIHO processing setup. Place the markers by hand instead." The
tracker finds no person at all (a very stylized character, a creature): "Could not find a body in the renders. Place the
markers by hand." Never an error with a traceback in it.

**Where it can go wrong, honestly.** Stylized characters: a chibi with a head half its height may fool a detector trained
on people. That is fine; Guess is a guess, the student drags what is wrong, and the preview catches the rest. A character
that is not standing roughly upright with the arms away from the body gets a poor guess; the handout says A-pose or
T-pose, which is also what the markers want. On an older classroom Mac the 2.0 setup may not be installed; the refusal
sentence handles it and nothing else breaks.

**What this does not do.** It does not place fingertips (section 4 does that from the mesh). It does not use the top
view (ARP does; our depth centering already answers the question the top view asks). It does not keep the renders.

**Why bother if Door B exists.** Door A is where every student's own character comes in. Guess plus mirrored markers
turns the dragging into a check, which is what ARP's users praise most. If David would rather keep Studio smaller,
this is the easiest build to postpone (section 8, build J) with nothing else depending on it. **Question 7.**

---

## 6. Bind fix-ups: plain names, and what each does with each engine

Six checkboxes under the Bind button, in this order. Four start ticked, two start unticked until they have been seen
working. Every name is a thing a student can picture; the hover text is the "does" column. Each pass runs after the
weights land, works on the vertex groups Blender already holds, and changes nothing about the skeleton.

| Checkbox (default) | What it does | With the voxel solver | With Automatic Weights |
|---|---|---|---|
| **Loose pieces on their own** (on) | Every separate piece of the character (a floating head, a detached hand, a hat) gets its weights from the bones that run through or next to it, never from a bone on the far side of the body. | The solver already treats pieces as one volume. This pass limits each piece's bones to those whose bounds touch the piece, then re-normalizes, so a hat cannot carry knee weight. | Blender weights each object alone against the whole rig and fails outright on a piece no bone passes through. This pass runs Automatic Weights per piece with only the nearby bones offered, and a piece that still gets nothing is given 100 percent to its nearest bone. |
| **Fix the size first** (on) | Characters that are very small or very large make the weight engines fail or go blotchy. The character and skeleton are scaled to about 2 m for the bind and scaled back after, invisibly. | The voxel grid (128 across) adapts to the bounds, so this mostly matters for the solver's falloff distance; applied for consistency. | This is the real fix for Blender's "bone heat weighting failed" on tiny characters. |
| **Soften the joints** (on) | Smooths the weights across each joint (shoulder, elbow, wrist, hip, knee, ankle) so the skin bends instead of creasing. One or two passes of neighbor averaging, limited to the band around the joint. | The solver's own falloff (0.2) already softens; this pass adds the joint band smoothing on top, clamped so the far ends of a limb stay firm. | Same pass on Blender's groups, which tend to be sharper at the joints. |
| **Hips hold the body** (on) | Makes sure the pelvis owns the belly and the hip region, so moving a thigh does not drag the stomach. Points above the hip line and inside the torso lose thigh weight to the pelvis and spine. | Needed: a wide-hipped or skirted character gets thigh weight up the torso from the solver's volume diffusion. | Needed less, but harmless. |
| **Heels stay put** (off until tested) | Gives the heel bone the sole of the foot below and behind the ankle, so the foot plants flat when Lock Feet holds it. | The solver splits the sole between shin, foot and heel bones; this pass hands the back of the sole to the heel bone. | Same. |
| **Head as one** (off until tested) | Everything above the neck pinch goes to the head and neck bones only, with no spine weight bleeding up, so a big head (the chibi) turns as one. | The neck pinch is already measured by the fit (the 1.4.5 silhouette rule); this pass uses that height as the cut. | Same. |

**Props** are not a checkbox but a tag, from the ActionForge study (gap 3): a small **Prop** checkbox appears per piece
in a list under the fix-ups, off by default. A tagged piece (a sword, a hat brim, glasses) skips the weight engine and
binds 100 percent to the one bone nearest its center, so it rides rigidly. One vertex group, no smoothing. The list
only draws when the character has more than one piece.

**Engine knobs stay hidden.** The solver's seven numbers (resolution 128, five diffuse loops, 64 rays, four bones per
point, falloff 0.2, sharpness 3, no solidify) stay as they are in `core/voxel_skinning.py`. Students never see them.
David can have them in the Diagnostics block later if a real character needs one changed.

**Names.** These are HIHO names for HIHO passes written fresh against the vendored MIT solver and Blender's own
operators. They are not ARP's code and not ARP's names (ARP's are Split Parts, Scale Fix, Smooth Twist Weights, Improve
Hips, Improve Heel, Refine Head). If David decides on study only (question 1), nothing in this table changes; the passes
are simple weight edits any rigger would write. If he allows GPL reuse, the only candidate worth reading before writing
is ARP's hips pass, and it would be read, not copied.

---

## 7. The panel, after all builds

Still behind the "Studio tools" checkbox at the bottom of the main panel until David says it is ready for a public
build (his 09-19 words: "its not gone, we just need the time to do the design and testing"). The promotion to a numbered
step of the main panel is the last build in section 8.

```
Studio                                   Everything here runs on this computer. Nothing is uploaded.

 1. Bring in your character
    [ Bring in a file ]  [ Use what is selected ]  [ Add the HIHO rig ]
    ( Turn arrows, only when the facing is unsure )
    ( Make it 1.7 m tall, only when the size is odd )

 2. Where are the joints?                     7 of 7 placed
    [ Guess ]  [ Place by hand ]
    [x] Mirrored        Left to Right  |  Right to Left   (only when unmirrored)
    > Fingers  (folded)   count [5]  [ Find fingertips ]

 3. Preview the skeleton
    [ Preview the skeleton ]   [ Hide markers ]

 4. Bind
    Engine: ( Auto | Voxel | Automatic Weights )
    [x] Loose pieces on their own   [x] Fix the size first
    [x] Soften the joints           [x] Hips hold the body
    [ ] Heels stay put              [ ] Head as one
    Props: [ ] Hat  [ ] Sword              (only with several pieces)
    [ Bind ]   [ Test pose ]

 5. Put the motion on it
    [ Load a take ]      Take: <folder>
    Character rig: [ picker ]
    [ Put the motion on it ]
    Then: step 6 in the main panel (Bake, Lock Feet, Save Out).

 Diagnostics (unchanged)
```

Door A walks 1, 2, 3, 4, 5. Door B walks 1 (Add the HIHO rig, model, Use what is selected), 4, 5; steps 2 and 3 grey out
with the hover text "Not needed: your character is built around the HIHO rig."

Hover text follows the 09-19 discipline: one sentence, what the button does, in these words. The status line at the top
of the main panel carries every "after" sentence from section 2.

---

## 8. Build list: one zip per change, a check for each

Numbers are the next free ones when each is built (1.5.9 is already spoken for by David's wrist-limit pick, and the two
parity one-liners may take one more). Order matters only where noted. Every build: headless test on Blender 5.2 LTS with
`--factory-startup` from source, then David's live run on the chibi, then the zip is built from `SOFTWARE/` with
`build_zip.py` and installed. Every build re-runs the July end-to-end on the chibi (bring in, markers, rig, load the
09-19 take, motion on it, bake, save out) as its regression, because that chain is the product.

**Before any build: the test David named in the ActionForge study.** Run today's Studio pipeline on two or three real
student characters, not the chibi (the ART 102 A2 blockouts due Sunday 10/18, with the students' permission; names
never enter a doc or the repo). Log each in take-log style: his words, what broke. That log reorders this list.

| Build | Change (one thing) | Check |
|---|---|---|
| **A. Words and order** | Studio panel redrawn as the five steps with today's operators behind them, new hover text, the "nothing is uploaded" line, the status sentences. No logic changes. | Headless: panel draws with the box on, refuses to draw with it off (as 1.5.3). Live: screenshot for David's eye. The chibi chain still runs. |
| **B. Bring in your character** | Normalize on import (apply transforms, feet on the floor, middle on the origin, facing check, units check), `.glb` accepted, Use what is selected, the foreign-rig refusal moved here, the size offer. | Headless: a chibi saved rotated 90 degrees, scaled 5x, floating at 3 m lands upright, 1 unit scale, feet at zero, facing minus Y; a Mixamo FBX is refused with the exact sentence; a 0.1 m model triggers the size offer and it scales to 1.7 m. Live: David brings in a student blockout. |
| **C. Mirrored markers and the counter** | Mirrored checkbox on by default, seven markers shown, right side follows live; the counter; depth centering moves to marker release. | Headless: place seven, read thirteen; turn Mirrored off, all thirteen draw; counter reads "7 of 7" only after each has moved. Live: he places seven on the chibi and watches them snap into the body. |
| **D. Preview the skeleton** | Auto-Rig splits in two: Preview the skeleton (fit only, replaceable) and Bind (weights). Missing-marker refusal by plain name. | Headless: preview builds 23 bones, zero vertex groups on the mesh; re-preview after moving a marker replaces the rig (one rig in the scene); the refusal names "Left Knee". Live: he nudges and re-previews on the chibi. |
| **E. Bind with Auto engine and the first two fix-ups** | Engine Auto rule; "Loose pieces on their own" and "Fix the size first"; fallback message kept. | Headless: the eight-piece July smoke chibi binds with Voxel under Auto, a one-piece Suzanne body with Automatic; the hat piece has no knee weight; a 0.1 m copy binds under Automatic without the heat failure. Compare against July's `comparison.blend`. Live: his chibi. |
| **F. The other four fix-ups** | Soften the joints, Hips hold the body, Heels stay put, Head as one. | Headless: pose the elbow 90 degrees, measure the crease (max angle between adjacent face normals across the joint) before and after Soften; thigh weight above the hip line is zero after Hips; sole-back points belong to the heel; nothing above the pinch has spine weight. Live: Test pose on the chibi, his eye. |
| **G. Test pose** | The three-second wiggle, start and stop, throwaway action removed on stop. | Headless: action exists while playing, gone after, rest pose restored exactly (bone matrices equal). Live: he watches the chibi wiggle. |
| **H. The shipped blockout rig** | `diagnostics/make_blockout_rig.py`, the `assets/HIHO_Rig_Apose_v1.blend` file, `build_zip.py` includes `assets/`, "Add the HIHO rig" button, Bind detects the tag, skips the fit, refuses uneven scale, applies uniform scale. | Headless: the asset has 63 bones, 0 constraints, 0 actions, 0 empties, feet at zero, upper arm 45 degrees below horizontal; a box-man built around the appended rig binds, Send to Character on the 09-19 take binds 63 bones with 0 skipped and the fingertips move; scaling the rig 2x then binding gives bone lengths 2x; uneven scale is refused with the sentence. Live: David models a quick body around it. |
| **I. Fingertips from the outline** (only if question 2 is yes) | The Fingers line, the finder, the finger chains, tip markers. | Headless: on a real hand mesh (Rigify reference) five tips found and named in order on both hands; on the chibi the count found is reported honestly; a mitten returns the count-0 message; Preview then builds 63 bones; Send to Character skips 0 fingers. Live: his eye on the chibi's hands in Test pose and on the take. |
| **J. Guess** | `external/guess_markers.py`, the two renders, the operator, confidence floor, the refusal when no setup is installed. | Outside Blender: the script on a saved pair of renders returns 13 joints with confidences in the marker protocol. Headless: on the chibi, each guessed marker within 5 percent of the character's height from David's hand placement from July (his marker positions are in the smoke-test blend); a scene with no setup path gets the refusal sentence. Live: Guess on a student character, then Preview. |
| **K. Props** | The per-piece Prop checkbox list, rigid bind to the nearest bone. | Headless: a cylinder "sword" near the right hand binds 100 percent to `hand.R`, one group, and follows it in Test pose. |
| **L. Promote Studio** | Studio becomes step 7, "Your character", of the main panel; the Studio tools checkbox keeps only Diagnostics. **Only when David says ready.** | Headless: the main panel draws seven steps; nothing behind the box but Diagnostics. Live: screenshot, his eye, then the class build. |

Not in this list, by design: a starter clip library (the 09-19 take shipped as a loadable take, A-pose only, from the
ActionForge study gap 1), the Mixamo-rigged door (gap 2), export renaming (gap 4), and the 1.4.6 head-bone layout. Each
is its own design note when David asks.

**Timing.** December and January, before the Spring term (classes start Wednesday, January 27). A through H are the
class-critical set; I, J, K are the ARP-parity set and can land after the first demo day if time runs short.

---

## 9. Questions for David

1. **Study only, or reuse GPL-3 code from ARP or Easy Rigify?** Carried from the state-of-the-art doc; recommendation
   stays study only. This design needs nothing from either codebase; question 1 only changes whether I read ARP's hips
   pass before writing ours.
2. **Fingers on the Door A auto-rig (section 4, build I), or is Door B's free 63-bone rig enough for the class?** If
   Door B is the class default and student-made characters are the exception, I would park build I until a student asks
   for fingers on their own character.
3. **The Easy Rigify seat ($30) to read its detection code.** Nothing here waits on it.
4. **May "Bring in your character" apply transforms and move the character to the floor without asking?** July said no.
   Every rigging tool does it. Proposal: yes for a file just imported, and say what was done in the status line for a
   selection already in the scene.
5. **Proportions for the shipped rig: his 09-19 take (proposal), or wait for a student take and ship two files later?**
   And the file name: `HIHO_Rig_Apose_v1.blend`, rig called `HIHO_Rig`.
6. **Is the grown chibi in the cold-storage pen the dummy body, modeled around the shipped rig?** If yes, David moves it
   out of the pen (Claude does not touch the pen) and it becomes the first Door B character and the test body for builds
   E through H.
7. **Guess (section 5, build J): build it for Spring, or postpone?** It is the one build with a new external script, and
   the one that depends on the processing setup being installed on classroom machines.
8. **Engine: show the Auto / Voxel / Automatic choice, or hide it and only say which one ran?** Proposal: show it, Auto
   selected, so a student who reads the status line can override.
9. **Which fix-ups start ticked?** Proposal: the first four on, Heels and Head off until seen working on the chibi.
10. **The test pose: a canned wiggle (proposal), or a short loop from his own 09-19 take cut to three seconds?** The take
    version needs the take loaded, which breaks the order; the wiggle needs nothing.
11. **The words.** "Bring in your character", "Where are the joints?", "Preview the skeleton", "Bind", "Put the motion
    on it", "Add the HIHO rig", "Test pose", the six fix-up names, "Prop". His call on every one, in his words.
12. **When does Studio stop hiding behind the checkbox?** Proposal: after build H passes on a real student character,
    and before the first demo day.

---

## 10. What this design does not change

The capture, calibration, processing and mocap rig code. The rotation-copy retarget and its hip-height scaling. The
vendored solver and its seven numbers. The marker identity scheme. The 63-bone rig, its names, its rest tables and its
constraint stack (1:1 with upstream stays the rule; the shipped asset is that rig with the constraints stripped, not a
new skeleton). Bake, Lock Feet, Save Out. The Diagnostics block. The wrist-limit decision, which is its own build and
comes first.
