# One Collection Per Take — design draft (2026-10-02, BASEMENT, laptop)

Status: DRAFT from David's words during the 10-02 recording session. No code. Waits for his answers in section 5.
David, same session: "I'm not trying to solve that issue necessarily in this session... I want us to start focusing
on a blend file that maybe contains multiple recordings." So: direction set, build later. For the rest of 10-02 he
works one file per take (saved the first as a HIHO in-progress mocap file, then File > New).

## 1. The problem, in David's words

> "If we actually get a flow going and we're getting multiple takes, it's a little awkward if the rig, the first one,
> shows up at the world origin point. And then what happens when we re-record? ... Otherwise you're going to get
> multiple recordings showing up on the same spot in the world origin point. Students can get really confused
> quickly when things visually look abnormal. We want to keep that workspace as clear as possible."

What the addon does today (1.5.6), checked in the code:

- Spawn Rig names the skeleton after the take folder (`HIHO_MOCAP_Rig_<take>`), so a second take never overwrites
  the first. Good.
- But every take's skelly root, its tracking empties and its rig are linked into **whatever collection is active**
  (`core/output_rig.py:112,126` use `bpy.context.collection`), usually the default "Collection". Every take lands
  at the world origin, on top of the last one. Nothing is hidden, nothing is grouped.
- Camera video planes already have their own collection, "HIHO MOCAP Videos" (`core/video_planes.py:20`), shared
  by all takes, so the planes from two takes also pile up.
- Spawning the SAME take again purges that take's old rig first (`operators/spawn_rig.py:109`). Keep that.

## 2. David's design, in his words

> "Once Process Mocap is processed, it's put into a collection. That collection has a date, and that all can be
> turned on and off. When we record again and spawn a new rig, it automatically closes that previous collection to
> make way for the new one."

> "If we're starting a new project, we need to clear the workspace, right?"

## 3. Proposed behaviour (translation of section 2)

1. **Spawn Rig puts everything for a take into one collection named after the take**, e.g.
   `HIHO Take 2026-10-02_14-28-01`. Inside: the skelly root, its empties, the rig. If Add Camera Videos is pressed
   for that take, its planes go in there too (not the shared Videos collection).
2. **When a new take's collection is created, every older HIHO take collection is hidden** (eye off in the
   outliner, and off in renders). They stay in the file; one click on the eye brings a take back.
3. **The outliner is the take list.** Students see one row per take, dated, newest at the bottom, only the newest
   visible. Nothing to learn beyond "the eye icon".
4. **Load Take (Studio tools) behaves the same way** as Spawn Rig: it is the same convergence point in the code.
5. **"Clear the workspace" for a new project = File > Save As with a new name, then delete the old take
   collections you do not want** (right-click > Delete Hierarchy). Or: a button. See question 5.4.

## 4. Why this is the right layer

- Collections are the Blender-native "group + hide" and students meet them on day one in ART 102. No new concept.
- Hiding, not deleting: a take is never lost by pressing Record again. Matches "Claude never deletes" at the
  file level too.
- One change: the two `bpy.context.collection` links in `output_rig.py` plus the rig link in `build_rig.py` become
  "link into this take's collection". The hide-previous step is a loop over collections named `HIHO Take *`.
  Small build, its own version number.

## 5. Decisions for David (answer in plain words, I translate)

5.1 **Name on the collection.** Just the take folder (`HIHO Take 2026-10-02_14-28-01`), or shorter
    (`Take 2:28 PM Oct 2`)? The folder name is what the recording report and the take log use.

5.2 **Hidden how?** Eye off (hidden but still loaded, one click back) vs excluded (checkbox off; lighter for the
    computer on long sessions, but the rig also leaves the timeline and the dope sheet). Default proposal: eye off.

5.3 **Camera videos.** Per-take collection (proposal) or keep the shared "HIHO MOCAP Videos" collection?

5.4 **A "New Session" button?** Proposal: NO button for now. Save As + delete the old collections is a Blender skill
    students should have anyway, and a button that deletes things is exactly what the never-delete rule is wary of.
    Could become "Archive takes" later (moves old take collections into one folder collection, still hidden).

5.5 **Bake + Export.** Baking pushes the take's clip onto the character (see the Bake to NLA note). Should the take
    collection stay hidden after bake, or does Bake not care? Proposal: Bake does not touch collections.

5.6 **Re-spawning the same take.** Keep today's rule (replace that take's rig) and keep its collection, just refill it.

## 6. Out of scope here

The empty-panel-on-new-file bug (BUGS_AND_BACKLOG 2026-10-02 #3) is a separate build: this doc is about one
file with many takes, that one is about a new file.
