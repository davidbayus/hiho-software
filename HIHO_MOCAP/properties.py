"""Scene-level properties for HIHO MOCAP — the settings the student adjusts."""

import bpy


def _is_armature(self, obj):
    return obj.type == 'ARMATURE'


class HIHO_MOCAP_PG_settings(bpy.types.PropertyGroup):
    """Settings shown in the HIHO MOCAP N-panel. Lives on the Scene as `scene.hiho_mocap`."""

    countdown_seconds: bpy.props.IntProperty(
        name="Countdown",
        description="Seconds to count down before recording starts",
        default=15,
        min=0,
        max=60,
    )
    record_length_seconds: bpy.props.IntProperty(
        name="Length",
        description="Recording length in seconds",
        default=60,
        min=1,
        max=600,
    )
    last_take_path: bpy.props.StringProperty(
        name="Take folder",
        description="Folder containing the Camera_*.mp4 files to process. Record sets this automatically; you can also pick an older take.",
        default="",
        subtype='DIR_PATH',
    )
    last_processed_path: bpy.props.StringProperty(
        name="Processed take",
        description=(
            "The 3D landmarks .npy that Spawn Rig builds from. Process Mocap "
            "sets this automatically; you can also pick the .npy of an older "
            "processed take (inside its output_data folder)."
        ),
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
        description=(
            "Optional override for the FreeMoCap calibration TOML. "
            "Leave blank to auto-use last_successful_calibration.toml."
        ),
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
        description=(
            "Which camera indices to record, comma-separated. Easiest way to set "
            "it: click Show Cameras and right-click the cameras you want in or "
            "out — this box fills in when you close that window. Camera numbers "
            "can shuffle after a reboot or replug, so confirm before recording. "
            "Left blank, Record refuses and sends you to Show Cameras."
        ),
        default="",
    )

    calibration_take_path: bpy.props.StringProperty(
        name="Calibration take",
        description="Folder of recorded Charuco-board videos to solve into a calibration. Record Calibration sets this; you can also pick an older board take.",
        default="",
        subtype='DIR_PATH',
    )

    charuco_square_mm: bpy.props.FloatProperty(
        name="Square size (mm)",
        description="Width of one black square on the printed Charuco board, measured with a ruler in millimeters. The house board is 200. A wrong value scales the whole capture uniformly (heights, distances) without changing the quality score.",
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
        description="File format for Save Out",
        items=[
            ('FBX', "FBX", "Game-engine-friendly animation file"),
            ('GLB', "GLB", "Lightweight web/game animation file"),
            ('BLEND', ".blend", "Native Blender file"),
        ],
        default='FBX',
    )
    show_science_mode: bpy.props.BoolProperty(
        name="Show Science Mode",
        description="Show the technical panel (Capture, Calibrate, Process, Output, Face). Leave off for the five Studio steps only",
        default=False,
    )


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
    )

    def draw(self, context):
        self.layout.prop(self, "freemocap_env_python")
        self.layout.prop(self, "data_home")
