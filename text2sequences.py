"""Text-to-sequences Blender add-on."""

import re

import bpy
import bpy_extras


bl_info = {
    "name": "Text to sequences",
    "description": (
        "Select a group of movie strips and create sequences based on time"
        " marks defined in a simple text file."
    ),
    "author": "mondeja",
    "license": "BSD-3-Clause",
    "category": "Sequencer",
    "version": (0, 0, 1),
    "blender": (3, 3, 0),
    "support": "COMMUNITY",
}

FPS = 60
X_OFFSET_FRAMES_SPACE_TO_DRAW = 10000


def time_string_to_frames(time_string):
    """Converts a time string to frames."""
    if "." in time_string:
        time_string, miliseconds = time_string.split(".")
        ms_frames = int(int(miliseconds) / 1000 * FPS)
    else:
        ms_frames = 0

    time_parts = time_string.split(":")
    if len(time_parts) == 3:  # noqa: PLR2004
        hours, minutes, seconds = time_parts
    elif len(time_parts) == 2:  # noqa: PLR2004
        hours, minutes, seconds = 0, time_parts[0], time_parts[1]
    else:
        raise ValueError("Invalid time string")

    return (
        ms_frames + (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * FPS
    )


def get_selected_sequences_number_by_order(context):
    result = {}
    seq_number = 1

    for sequence in context.selected_sequences:
        if sequence.type == "MOVIE":
            result[seq_number] = [sequence]
            for other_seq in context.selected_sequences:
                if (
                    other_seq.type == "SOUND"
                    and sequence.channel - other_seq.channel == 1
                    and (
                        sequence.name.split(".")[0]
                        == other_seq.name.split(".")[0]
                        or (
                            other_seq.frame_final_start
                            == sequence.frame_final_start
                            and other_seq.frame_final_end
                            == sequence.frame_final_end
                        )
                    )
                ):
                    result[seq_number].append(other_seq)
            seq_number += 1
    return result


def read_marks_from_text_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]

    time_marks = []
    for line_index, line in enumerate(lines):
        if line.strip() == "" or line.strip().startswith("#"):
            continue

        time_mark = []
        line_parts = line.replace("\t", " ").split(" ")
        for i, part in enumerate(line_parts):
            if i == 0 or re.match(r"^\d+$", part):  # number
                time_mark.append(int(part))
            elif re.match(r"^(\d+:)?\d+:\d+(\.\d+)?$", part):  # hour
                try:
                    frames = time_string_to_frames(part)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid time string at {filepath}:{line_index + 1}"
                        f" for value '{part}' in line '{line}'",
                    ) from exc
                time_mark.append(frames)
            else:
                raise ValueError(
                    f"Invalid time mark at {filepath}:{line_index + 1}"
                    f" for value '{part}' in line '{line}'",
                )

        time_marks.append(time_mark)
    return time_marks


def get_y_offset_of_first_free_channel_for_selection(context):
    """Returns the first channel with space for new channels."""
    selected_sequences = context.selected_sequences
    first_selected_channel = min([seq.channel for seq in selected_sequences])
    last_selected_channel = max([seq.channel for seq in selected_sequences])

    first_free_channel = last_selected_channel + 1
    for seq in context.sequences:
        if seq.channel >= first_free_channel:
            first_free_channel = seq.channel + 1

    return first_free_channel - first_selected_channel


def max_sequence_frames(sequences):
    return max(
        [seq.frame_final_end - seq.frame_final_start for seq in sequences],
    )


class Text2Sequences(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """Text-to-sequences Blender operator."""

    bl_idname = "sequencer.text2sequences"
    bl_label = "Text to sequences"

    filter_glob: bpy.props.StringProperty(
        default="*.text;*.txt;",
        options={"HIDDEN"},
    )

    mute_original_sequences: bpy.props.BoolProperty(
        name="Mute original sequences",
        description="Mute original sequences after creating the new.",
        default=False,
    )

    mute_new_sequences: bpy.props.BoolProperty(
        name="Mute new sequences",
        description="Mute new sequences after creating them.",
        default=False,
    )

    select_new_sequences: bpy.props.BoolProperty(
        name="Select new sequences",
        description="Select new sequences after creating them.",
        default=True,
    )

    def execute(self, context):  # noqa: PLR0912, PLR0915
        """Execute the operator."""
        before_execute_sequence_names = [seq.name for seq in context.sequences]
        before_execute_overlap_mode = (
            context.scene.tool_settings.sequencer_tool_settings.overlap_mode
        )
        context.scene.tool_settings.sequencer_tool_settings.overlap_mode = (
            "SHUFFLE"
        )

        try:
            time_marks = read_marks_from_text_file(self.filepath)
        except ValueError as exc:
            self.report({"ERROR_INVALID_INPUT"}, str(exc))
            return {"CANCELLED"}

        sequences_by_order_number = get_selected_sequences_number_by_order(
            context,
        )
        for time_mark in time_marks:
            try:
                seqs = sequences_by_order_number[time_mark[0]]
            except KeyError:
                self.report(
                    {"ERROR_INVALID_INPUT"},
                    (
                        f"Sequence number {time_mark[0]} not found in"
                        " selection. Check that you've selected sounds"
                        " along with their movie clips."
                    ),
                )
                return {"CANCELLED"}
            else:
                time_mark.append(seqs)

        if self.mute_original_sequences:
            bpy.ops.sequencer.mute(unselected=False)

        selection_copy_offset_y = (
            get_y_offset_of_first_free_channel_for_selection(
                context,
            )
        )
        last_channel_frame_end = 0
        start_frame = None

        # For each time mark, create a new sequence
        for i, (n_sequence_channel, frame_start, frame_end, seqs) in enumerate(
            time_marks,
        ):
            for seq in context.selected_sequences:
                seq.select = False
            for seq in seqs:
                seq.select = True

            seqs_max_frames = max(
                [seq.frame_final_end - seq.frame_final_start for seq in seqs],
            )
            min_start_frame = min([seq.frame_final_start for seq in seqs])
            min([seq.channel for seq in seqs])
            if start_frame is None:
                start_frame = min_start_frame

            offset_y = (
                selection_copy_offset_y
                + (2 if i % 2 == 0 else 0)
                + ((n_sequence_channel - 1) * 2)
            ) - 2

            # Copy all selected clips and move to the outputs
            bpy.ops.sequencer.duplicate_move()
            bpy.ops.transform.seq_slide(
                value=(
                    -seqs_max_frames + X_OFFSET_FRAMES_SPACE_TO_DRAW,
                    offset_y,
                ),
                snap=False,
            )

            if self.mute_original_sequences:
                bpy.ops.sequencer.unmute()

            # Split sequences
            selected_seqs_names = [
                seq.name for seq in context.selected_sequences
            ]
            before_split_seqs_names = [seq.name for seq in context.sequences]

            channel = context.selected_sequences[0].channel
            start_split, end_split = (
                frame_start + start_frame,
                frame_end + start_frame,
            )

            bpy.ops.sequencer.split(
                frame=start_split + X_OFFSET_FRAMES_SPACE_TO_DRAW,
                channel=channel,
            )
            bpy.ops.sequencer.split(
                frame=end_split + X_OFFSET_FRAMES_SPACE_TO_DRAW,
                channel=channel,
            )
            # Delete last sequence (at the right of the split)
            bpy.ops.sequencer.delete()

            # Remove original sequences
            new_sequences = []
            for seq in context.sequences:
                seq.select = False
                if seq.name in selected_seqs_names:
                    seq.select = True
                elif seq.name not in before_split_seqs_names:
                    new_sequences.append(seq)
            bpy.ops.sequencer.delete()

            # Move new sequences
            for seq in new_sequences:
                seq.select = True
            bpy.ops.transform.seq_slide(
                value=(
                    -frame_start
                    + last_channel_frame_end
                    - X_OFFSET_FRAMES_SPACE_TO_DRAW,
                    0,
                ),
                snap=False,
            )

            # Save last channel frame end
            last_channel_frame_end = (
                last_channel_frame_end + frame_end - frame_start
            )

        context.scene.tool_settings.sequencer_tool_settings.overlap_mode = (
            before_execute_overlap_mode
        )

        new_sequences = [
            seq
            for seq in context.sequences
            if seq.name not in before_execute_sequence_names
        ]

        for seq in new_sequences:
            seq.select = True
        if self.mute_new_sequences:
            bpy.ops.sequencer.mute(unselected=False)
        else:
            bpy.ops.sequencer.unmute()

        if not self.select_new_sequences:
            for seq in new_sequences:
                seq.select = False

        return {"FINISHED"}

    @classmethod
    def poll(cls, context):
        """Enable operator when at least one movie clip is selected.

        https://docs.blender.org/api/current/bpy.types.Sequence.html#bpy.types.Sequence.type
        """
        return len(context.selected_sequences) > 0 and (
            all(
                sequence.type in ("MOVIE", "SOUND")
                for sequence in context.selected_sequences
            )
        )


# Only needed if you want to add into a dynamic menu
def menu_func_import(self, _context):
    self.layout.operator(
        Text2Sequences.bl_idname,
        text="Text to sequences",
        icon="CAMERA_DATA",
    )


def register():
    bpy.utils.register_class(Text2Sequences)
    bpy.types.SEQUENCER_MT_add.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(Text2Sequences)
    bpy.types.SEQUENCER_MT_add.remove(menu_func_import)


if __name__ == "__main__":
    register()
