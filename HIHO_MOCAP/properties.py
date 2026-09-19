"""Scene-level properties for HIHO MOCAP — the settings the student adjusts."""

import os

import bpy


def _is_armature(self, obj):
    return obj.type == 'ARMATURE'


class HIHO_MOCAP_PG_settings(bpy.types.PropertyGroup):
    """Settings shown in the HIHO MOCAP N-panel. Lives on the Scene as `scene.hiho_mocap`."""

    countdown_seconds: bpy.props.IntProperty(
        name="Countdown",
        description="Seconds before a recording starts, so you can walk to your spot. Both Record buttons use this number",
        default=15,
        min=0,
        max=60,
    )
    record_length_seconds: bpy.props.IntProperty(
        name="Length",
        description="How long the performance recording runs, in seconds",
        default=60,
        min=1,
        max=600,
    )
    # Its own box (PANEL_REDESIGN_DESIGN_2026-09-19): one shared Length meant
    # typing 120 for the calibration dance, then remembering to change it back
    # before the performance. Every calibration take on disk was set to 120.
    calibration_length_seconds: bpy.props.IntProperty(
        name="Length",
        description="How long the calibration recording runs, in seconds. The calibration dance needs 120",
        default=120,
        min=1,
        max=600,
    )
    # Per FILE on purpose (V2_CHANGEOVER_DESIGN_2026-09-18, Q2): every new
    # .blend starts on RTMPose, so a forgotten switch to the slow tracker can
    # never follow the next student.
    tracker: bpy.props.EnumProperty(
        name="Tracker",
        description="Which tracker Process Mocap runs. Every new file starts on RTMPose",
        items=[
            ('RTMPOSE', "RTMPose (fast)",
             "Looks at every camera at the same time. About 3 minutes for a 30 second take"),
            ('MEDIAPIPE', "MediaPipe (classic, slow)",
             "Looks at one camera at a time. About 13 minutes for a 30 second take. "
             "The known-good fallback"),
        ],
        default='RTMPOSE',
    )
    last_take_path: bpy.props.StringProperty(
        name="Take folder",
        description="The recording to process. It fills in by itself after Record Mocap. Change it only to process an older take",
        default="",
        subtype='DIR_PATH',
    )
    last_processed_path: bpy.props.StringProperty(
        name="Processed take",
        description="The processed take the rig is built from. It fills in by itself after Process Mocap. Change it only to load an older take",
        default="",
        subtype='FILE_PATH',
    )
    face_take_csv: bpy.props.StringProperty(
        name="Face take",
        description=(
            "The face recording's CSV from the phone (Live Link Face app). "
            "AirDrop the take to this computer, then pick its _cal.csv "
            "(best) or _raw.csv here."
        ),
        default="",
        subtype='FILE_PATH',
    )
    flash_body_frame: bpy.props.FloatProperty(
        name="Body flash frame",
        description="Playhead frame where the flash appears in the camera "
                    "video planes. Set by Mark Flash (Body); -1 = not marked.",
        default=-1.0,
    )
    flash_face_frame: bpy.props.FloatProperty(
        name="Face flash frame",
        description="Playhead frame where the flash appears in the face "
                    "video plane. Set by Mark Flash (Face); -1 = not marked.",
        default=-1.0,
    )
    face_flash_offset_at_mark: bpy.props.FloatProperty(
        name="Face offset at mark",
        description="How far the face take was already shifted when its "
                    "flash was marked. Bookkeeping for Line Up Face: makes "
                    "re-marking correct the sync instead of compounding it.",
        default=0.0,
    )
    face_applied_offset: bpy.props.FloatProperty(
        name="Face offset",
        description="How many frames Line Up Face has shifted the face take. "
                    "0 = not lined up yet.",
        default=0.0,
    )
    calibration_toml_path: bpy.props.StringProperty(
        name="Calibration",
        description="The calibration to use. Leave it blank to use the one you just solved",
        default="",
        subtype='FILE_PATH',
    )
    freemocap_env_python: bpy.props.StringProperty(
        name="FreeMoCap env (deprecated)",
        description=(
            "Deprecated - this setting moved to the add-on Preferences "
            "(Edit > Preferences > Add-ons > HIHO MOCAP) so it survives new "
            "files. This per-scene copy is ignored; kept so old .blend files "
            "load without complaints."
        ),
        default="",
    )
    camera_ids: bpy.props.StringProperty(
        name="Cameras",
        description="The cameras that will record. It fills in by itself when you close the Show Cameras window",
        default="",
    )

    calibration_take_path: bpy.props.StringProperty(
        name="Calibration take",
        description="The calibration recording to solve. It fills in by itself after Record Calibration. Change it only to solve an older one again",
        default="",
        subtype='DIR_PATH',
    )

    charuco_square_mm: bpy.props.FloatProperty(
        name="Square size (mm)",
        description="Width of one black square on the board, in millimeters. The house board is 200. Leave it alone unless you use a different board",
        default=200.0,
        min=10.0,
        max=500.0,
        precision=1,
    )

    # --- Calibration quality (set by Check Calibration, shown as a badge) ---
    calibration_quality_px: bpy.props.FloatProperty(
        name="Calibration quality (px)",
        description="Mean reprojection error of the current calibration. Lower is better. -1 = not checked yet.",
        default=-1.0,
    )
    calibration_verdict: bpy.props.StringProperty(
        name="Calibration verdict",
        description="Plain-English calibration quality: excellent / good / workable / recalibrate",
        default="",
    )
    groundplane_status: bpy.props.StringProperty(
        name="Floor status",
        description="Floor (groundplane) verdict from the last Solve. Starts with OK when "
                    "the floor and up-axis came from the board's opening floor position, "
                    "FAILED when they didn't. Full text in the take folder's "
                    "GROUNDPLANE_STATUS.txt.",
        default="",
    )
    calibration_badge_take: bpy.props.StringProperty(
        name="Quality badge take",
        description="Which board take the Quality badge describes (folder name). "
                    "Blank when the scored calibration file doesn't carry a take name.",
        default="",
    )
    groundplane_badge_take: bpy.props.StringProperty(
        name="Floor badge take",
        description="Which board take the Floor badge describes (folder name).",
        default="",
    )
    volume_verdict: bpy.props.StringProperty(
        name="Volume map verdict",
        description="Clean-radius verdict from Map the Volume, named for its take. "
                    "Full numbers in the take folder's VOLUME_MAP.txt.",
        default="",
    )
    volume_map_path: bpy.props.StringProperty(
        name="Volume map image",
        description="The volume_map.png Map the Volume last saved.",
        default="",
    )
    process_verdict: bpy.props.StringProperty(
        name="Process quality",
        description="Solve quality of the last processed take, from its mean reprojection error. Full numbers in the take folder's PROCESS_QUALITY.txt.",
        default="",
    )
    process_badge_take: bpy.props.StringProperty(
        name="Process badge take",
        description="Which take the Process quality badge describes (folder name).",
        default="",
    )
    process_badge_tracker: bpy.props.StringProperty(
        name="Process badge tracker",
        description="Which tracker made the result the Process quality badge describes.",
        default="",
    )

    # --- Studio Panel (v1.4 character pipeline) ---
    character_collection: bpy.props.StringProperty(
        name="Character collection",
        description="Collection holding the imported character. Import Character sets this automatically.",
        default="",
    )
    skinning_mode: bpy.props.EnumProperty(
        name="Skinning",
        description="How Auto-Rig glues the mesh to the bones",
        items=[
            ('VOXEL', "Voxel", "HIHO's bundled voxel solver — best for characters built from separate pieces (falls back to Automatic if it fails)"),
            ('AUTOMATIC', "Automatic", "Blender's built-in Automatic Weights — fine for clean single-piece characters"),
        ],
        default='VOXEL',
    )
    marker_mirror_axis: bpy.props.EnumProperty(
        name="Mirror axis",
        description="Which world axis the character's left/right sides face across (X if the character faces front/-Y, Y if it faces sideways)",
        items=[
            ('X', "X", "Character's sides differ along the X axis (facing front, the usual case)"),
            ('Y', "Y", "Character's sides differ along the Y axis (facing sideways)"),
        ],
        default='X',
    )

    # --- Studio Panel (v1.2) ---
    character_target: bpy.props.PointerProperty(
        name="Character",
        description="Armature to drive with the baked motion capture animation",
        type=bpy.types.Object,
        poll=_is_armature,
    )
    export_format: bpy.props.EnumProperty(
        name="Format",
        description="The file type Save Out writes. FBX for game engines, GLB for the web, .blend for Blender",
        items=[
            ('FBX', "FBX", "Game-engine-friendly animation file"),
            ('GLB', "GLB", "Lightweight web/game animation file"),
            ('BLEND', ".blend", "Native Blender file"),
        ],
        default='FBX',
    )


def _data_home_update(self, context):
    """Rewrite "Save to" in place when the picker landed inside HIHO_CAPTURES /
    HIHO_CALIBRATIONS, so the field shows the folder takes will really use."""
    from .operators import climb_to_data_home, norm_path
    fixed = climb_to_data_home(norm_path(self.data_home))
    if fixed and os.path.normpath(norm_path(self.data_home)) != fixed:
        self.data_home = fixed


class HIHO_MOCAP_AddonPreferences(bpy.types.AddonPreferences):
    """Machine-level settings. Scene properties reset to defaults in every new
    .blend, which silently re-pointed the env path on student machines (audit
    M18); preferences are saved with Blender itself — set once per machine."""

    bl_idname = __package__

    freemocap_env_python: bpy.props.StringProperty(
        name="FreeMoCap env",
        description=(
            "Python of the external FreeMoCap environment that records and "
            "processes outside Blender. This is what lets Blender run any "
            "current version instead of being pinned to an old one. "
            "Set once per machine."
        ),
        # TODO: today defaults to David's freemocap-env. For students this becomes
        # an auto-detect / "Install FreeMoCap" step (see headless design doc).
        default="/Users/davidbayus/miniforge3/envs/freemocap-env/bin/python",
        subtype='FILE_PATH',
    )

    fmc2_env_python: bpy.props.StringProperty(
        name="FreeMoCap 2.0 env",
        description=(
            "Python of the FreeMoCap 2.0 environment that runs the RTMPose "
            "tracker. Recording and calibration keep using the FreeMoCap env "
            "above. Set once per machine."
        ),
        # TODO (1.5.3): HIHO Setup installs 2.0 into a fixed home and this
        # default points there. Until then it is the eval kit's env.
        default="~/Desktop/HIHO_ALL/RTMPOSE_EVAL/LOCAL.nosync/freemocap-2.0a23/.venv/bin/python",
        subtype='FILE_PATH',
    )

    data_home: bpy.props.StringProperty(
        name="HIHO data home",
        description=(
            "Folder that holds HIHO_CAPTURES and HIHO_CALIBRATIONS. Every "
            "recording and calibration saves under it. Default is the "
            "Desktop; point it at your own working folder if you keep HIHO "
            "material somewhere else. Set once per machine."
        ),
        default="~/Desktop",
        subtype='DIR_PATH',
        update=_data_home_update,
    )

    # The two opt-in checkboxes at the bottom of the panel
    # (PANEL_REDESIGN_DESIGN_2026-09-19, section 9). Per COMPUTER on purpose:
    # ticked once on the studio laptop they survive every new file, while a
    # student machine starts clean. The six steps of a session are never
    # behind either box; these only ADD unfinished tools on top.
    show_lock_feet: bpy.props.BoolProperty(
        name="Lock Feet (cleanup)",
        description=(
            "Show the Lock Feet button between Rig and Bake. It holds each "
            "foot to the floor while it is planted. Still being tested, so it "
            "starts switched off"
        ),
        default=False,
    )
    show_studio_tools: bpy.props.BoolProperty(
        name="Studio tools",
        description=(
            "Open the Studio panel: load a take, put the motion on your own "
            "character, and the diagnostic tools. Not finished yet, so it "
            "starts switched off"
        ),
        default=False,
    )

    def draw(self, context):
        self.layout.prop(self, "freemocap_env_python")
        self.layout.prop(self, "fmc2_env_python")
        self.layout.prop(self, "data_home")
        self.layout.prop(self, "show_lock_feet")
        self.layout.prop(self, "show_studio_tools")
