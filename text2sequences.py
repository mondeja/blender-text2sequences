"""Text-to-sequences Blender add-on."""

import io
import os.path
import re
import traceback

import bpy
import bpy_extras


bl_info = {
    "name": "Text2sequences",
    "description": (
        "Select a group of movie strips and create sequences based on time"
        " marks defined in a simple text file."
    ),
    "author": "mondeja",
    "license": "BSD-3-Clause",
    "category": "Sequencer",
    "version": (0, 0, 2),
    "blender": (3, 3, 0),
    "support": "COMMUNITY",
}

X_OFFSET_FRAMES_SPACE_TO_DRAW = 10000


def get_exception_traceback_str(exc: Exception) -> str:
    file = io.StringIO()
    traceback.print_exception(exc, file=file)
    return file.getvalue().rstrip()


def time_string_to_frames(time_string, fps, miliseconds_separator="."):
    """Converts a time string to frames."""
    if miliseconds_separator in time_string:
        time_string, miliseconds = time_string.split(miliseconds_separator)
        ms_frames = int(int(miliseconds) / 1000 * fps)
    else:
        ms_frames = 0

    time_parts = time_string.split(":")
    if len(time_parts) == 3:  # noqa: PLR2004
        hours, minutes, seconds = time_parts
    elif len(time_parts) == 2:  # noqa: PLR2004
        hours, minutes, seconds = 0, time_parts[0], time_parts[1]
    else:
        raise ValueError("Invalid time string")

    return ms_frames + (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * fps


def get_selected_sequences_number_by_order(context):
    result = {}
    seq_number = 1

    for sequence in context.selected_sequences:
        if sequence.type != "MOVIE":
            continue

        result[seq_number] = [sequence]
        for other_seq in context.selected_sequences:
            if (
                other_seq.type == "SOUND"
                and sequence.channel - other_seq.channel == 1
                and (
                    sequence.name.split(".")[0] == other_seq.name.split(".")[0]
                    or (
                        other_seq.frame_final_start == sequence.frame_final_start
                        and other_seq.frame_final_end == sequence.frame_final_end
                    )
                )
            ):
                result[seq_number].append(other_seq)
        seq_number += 1
    return result


def normalize_text(value):
    return value.strip().replace("\t", " ")


def read_lines(filepath):
    with open(filepath, encoding="utf-8") as f:
        for line in f.readlines():
            if "#" in line:
                new_line = normalize_text(line.split("#")[0].strip())
            else:
                new_line = normalize_text(line.strip())
            if new_line != "":
                yield new_line


def get_marks_from_text_lines(filepath, fps):
    time_marks = []
    for line_index, line in enumerate(read_lines(filepath)):
        time_mark = []
        for i, part in enumerate(line.split(" ")):
            if i == 0 or re.match(r"^\d+$", part):
                # frane or media container number
                time_mark.append(int(part))
            elif re.match(r"^(\d+:)?\d+:\d+(\.\d+)?$", part):
                try:
                    frames = time_string_to_frames(
                        part,
                        fps,
                        miliseconds_separator=".",
                    )
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


def get_marks_from_srt_lines(filepath, fps):
    time_marks = []
    inside_channel = None
    for line_index, line in enumerate(read_lines(filepath)):
        if line.isdigit():
            inside_channel = int(line)
        elif "-->" in line:
            time_mark = [inside_channel]
            for part in line.split("-->"):
                try:
                    frames = time_string_to_frames(
                        part.strip(),
                        fps,
                        miliseconds_separator=",",
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid time string at {filepath}:{line_index + 1}"
                        f" for value '{part}' in line '{line}'",
                    ) from exc
                else:
                    time_mark.append(frames)
            time_marks.append(time_mark)
    return time_marks


def get_y_offset_of_first_free_channel_for_sequences(context, sequences):
    """Returns the first channel with space for new channels."""
    first_free_channel = max([seq.channel for seq in sequences]) + 1
    for seq in context.sequences:
        if seq.channel >= first_free_channel:
            first_free_channel = seq.channel + 1

    return first_free_channel - min([seq.channel for seq in sequences])


def select_sequences(sequences):
    for seq in sequences:
        seq.select = True


def unselect_sequences(sequences):
    for seq in sequences:
        seq.select = False


class Text2Sequences(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """Text to sequences Blender operator."""

    bl_idname = "sequencer.text2sequences"
    bl_label = "Text to sequences"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: bpy.props.StringProperty(
        default="*.text;*.txt;*.srt;",
        options={"HIDDEN"},
    )

    select_new_sequences: bpy.props.BoolProperty(
        name="Select new sequences",
        description="Select new sequences after creating them.",
        default=True,
    )

    select_original_sequences: bpy.props.BoolProperty(
        name="Select original sequences",
        description="Select original sequences after creating the new ones.",
        default=False,
    )

    mute_original_sequences: bpy.props.BoolProperty(
        name="Mute original sequences",
        description="Mute original sequences after creating the new ones.",
        default=False,
    )

    mute_new_sequences: bpy.props.BoolProperty(
        name="Mute new sequences",
        description="Mute new sequences after creating them.",
        default=False,
    )

    def graceful_error(self, error_type, error_msg, state_backup, context):
        """Report an error and cancel the operator."""
        self.report({error_type}, error_msg)
        self.graceful_state_recovering(state_backup, context)
        return {"CANCELLED"}

    def graceful_state_recovering(self, state_backup, context):
        """Recover the state of the scene before the operator execution."""
        # Recover old overlap mode
        context.scene.tool_settings.sequencer_tool_settings.overlap_mode = state_backup[
            "overlap-mode"
        ]

        # Select previous selected sequences
        for seq in context.sequences:
            if seq.name not in state_backup["selected-sequence-names"]:
                seq.select = False
            else:
                seq.select = True

    def execute(self, context):
        """Execute the operator."""
        state_backup = {
            "sequence-names": [seq.name for seq in context.sequences],
            "selected-sequence-names": [seq.name for seq in context.selected_sequences],
            "overlap-mode": (
                context.scene.tool_settings.sequencer_tool_settings.overlap_mode
            ),
        }

        try:
            return self._execute_unsafe(context, state_backup)
        except Exception as exc:
            self.report({"ERROR"}, get_exception_traceback_str(exc))
            self.graceful_state_recovering(state_backup, context)
            return {"CANCELLED"}

    def _execute_unsafe(self, context, state_backup):  # noqa: PLR0912, PLR0915
        sequencer_tool_settings = context.scene.tool_settings.sequencer_tool_settings
        sequencer_tool_settings.overlap_mode = "SHUFFLE"

        first_movie_sequence_fps = None
        for seq in context.sequences:
            if seq.type == "MOVIE":
                first_movie_sequence_fps = int(seq.fps)
                break
        if first_movie_sequence_fps is None:
            return self.graceful_error(
                "ERROR_INVALID_INPUT",
                "No movie sequence found in the scene.",
                state_backup,
                context,
            )

        file_name, file_ext = os.path.splitext(self.filepath)

        try:
            if file_ext == ".srt":
                time_marks = get_marks_from_srt_lines(
                    self.filepath,
                    first_movie_sequence_fps,
                )
            else:
                time_marks = get_marks_from_text_lines(
                    self.filepath,
                    first_movie_sequence_fps,
                )
        except ValueError as exc:
            return self.graceful_error(
                "ERROR_INVALID_INPUT",
                str(exc),
                state_backup,
                context,
            )

        sequences_by_order_number = get_selected_sequences_number_by_order(
            context,
        )

        for time_mark in time_marks:
            try:
                seqs = sequences_by_order_number[time_mark[0]]
            except KeyError:
                return self.graceful_error(
                    "ERROR_INVALID_INPUT",
                    (
                        f"Sequence number {time_mark[0]} not found in"
                        " selection. Check that you've selected sounds"
                        " along with their movie clips."
                    ),
                    state_backup,
                    context,
                )
            else:
                time_mark.append(seqs)

        if self.mute_original_sequences:
            bpy.ops.sequencer.mute(unselected=False)

        selection_copy_offset_y = get_y_offset_of_first_free_channel_for_sequences(
            context,
            context.selected_sequences,
        )
        last_channel_frame_end = 0
        initial_frame = min([seq.frame_final_start for seq in time_marks[0][3]])

        # For each time mark, create a new sequence
        for i, (n_sequence_channel, frame_start, frame_end, seqs) in enumerate(
            time_marks,
        ):
            unselect_sequences(context.selected_sequences)
            select_sequences(seqs)

            seqs_n_frames = max(
                [seq.frame_final_end - seq.frame_final_start for seq in seqs],
            )

            offset_y = (
                selection_copy_offset_y
                + (2 if i % 2 == 0 else 0)
                + ((n_sequence_channel - 1) * 2)
            ) - 2

            # Copy all selected clips and move to the outputs
            bpy.ops.sequencer.duplicate_move()
            bpy.ops.transform.seq_slide(
                value=(
                    -seqs_n_frames + X_OFFSET_FRAMES_SPACE_TO_DRAW,
                    offset_y,
                ),
                snap=False,
            )

            if self.mute_original_sequences:
                bpy.ops.sequencer.unmute()

            # Split sequences
            selected_seqs_names = [seq.name for seq in context.selected_sequences]
            before_split_seqs_names = [seq.name for seq in context.sequences]

            channel = context.selected_sequences[0].channel
            bpy.ops.sequencer.split(
                frame=frame_start + initial_frame + X_OFFSET_FRAMES_SPACE_TO_DRAW,
                channel=channel,
            )
            bpy.ops.sequencer.split(
                frame=frame_end + initial_frame + X_OFFSET_FRAMES_SPACE_TO_DRAW,
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
            select_sequences(new_sequences)
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
            last_channel_frame_end = last_channel_frame_end + frame_end - frame_start

        sequencer_tool_settings.overlap_mode = state_backup["overlap-mode"]

        new_sequences = [
            seq
            for seq in context.sequences
            if seq.name not in state_backup["sequence-names"]
        ]

        select_sequences(new_sequences)
        if self.mute_new_sequences:
            bpy.ops.sequencer.mute(unselected=False)
        else:
            bpy.ops.sequencer.unmute()

        if not self.select_new_sequences:
            unselect_sequences(new_sequences)

        if self.select_original_sequences:
            select_sequences(
                [
                    seq
                    for seq in context.sequences
                    if seq.name in state_backup["sequence-names"]
                ],
            )

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
