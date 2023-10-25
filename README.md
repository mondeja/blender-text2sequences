# blender-text2sequences

![Blender >= v2.90](https://img.shields.io/badge/Blencer-%3E=2.90-blue?logo=blender&logoColor=white)

Blender add-on to select a group of strips and create sequences based on time marks defined in text files.

Ideal to create a first edition of a video based on a script or create video previews.

## Download

Download the addon using [the next link](https://github.com/mondeja/blender-text2sequences/releases/download/v0.0.6/text2sequences.py):

```
https://github.com/mondeja/blender-text2sequences/releases/download/v0.0.6/text2sequences.py
```

## Install

Under `Edit` -> `Preferences` -> `Add-ons`, press on `Install` and select the
downloaded file:

<p align="center">
  <img src="images/install-button.png">
</p>

Search for `text2sequences` in the search bar and enable the addon marking the
top-left checkbox:

<p align="center">
  <img src="images/enable-addon.png" width="80%">
</p>

## Usage

Create a `.txt` file and edit it with a content like:

```txt
1 00:01 00:03
2 00:02 00:04
1 00:03 00:05
2 00:02 00:04
1 00:01 00:02
```

Select two movie clips with their sound channels in the Video Sequence Editor:

<p align="center">
  <img src="images/select-sequences.png" width="80%">
</p>

Under `Add` menu, you can see that now the `Text to sequences` operator is enabled. Press it and open the text file with time marks. Press `Text to sequences` button and the result will be:

<p align="center">
  <img src="images/usage-result.png" width="80%">
</p>

### Explanation

The plugin builds a continuous sequence based on cuts of the original clips.

Channels 2 (movie) and 1 (sound), which compound the first media container channel, is named "1" in the text file and the channel 4 and 3 are "2".

In this example, a continous sequence will be generated from cuts of the original clips defined by time marks:

- `1 00:01 00:03` -> Cut from second 1 to second 3 of first movie (channels 2 and 1) and place from seconds 0 to 2 of the new sequence.
- `2 00:02 00:04` -> Cut from second 2 to second 4 of first movie (channels 4 and 3) and place from seconds 2 to 4 of the new sequence.
- ...

## Documentation

### Syntax

#### `.txt`

For _\*.txt_ files, time marks are defined each one in a line with the next format:

```txt
<media-container> <start-time> <end-time>
```

- `<media-container>` (_number_): Number of the media container (movie clip) to use. Starts in 1.
- `<start-time>` (_time_): Start time of the cut in the original clip.
- `<end-time>` (_time_): End time of the cut in the original clip.

Supports comments with `#` characters and fields separation by any number of spaces or tabs.

##### _time_

Mark times are defined in one of the next regular expressions:

```txt
# <minutes>:<seconds>(.<microseconds>)? (eg. 00:01 or 01:02.345)
(\d+:)?\d+:\d+(\.\d+)

# <hours>:<minutes>:<seconds>(.<microseconds>)? (eg. 00:01:02 or 01:02:03.456)
(\d+:)?\d+:\d+:\d+(\.\d+)

# <frames> (eg. 360 or 690)
\d+
```

##### Example

```txt
# This is a comment
1 00:01 00:03                # minutes:seconds
2 00:01.600 00:04.200        # minutes:seconds.microseconds
1 180 300                    # frames
2 00:05:04.100 00:06:07.300  # hours:minutes:seconds.microseconds
```

#### `.srt`

For _\*.srt_ files, time marks are defined in SRT format, changing the number of the subtitle by the number of the media container (movie sequence) to use. Subtitles values are ignored.

```txt
<media-container>
<start-time> --> <end-time>
```

- `<media-container>` (_number_): Number of the media container (movie clip) to use. Starts in 1.
- `<start-time>` (_SRT time_): Start time of the cut in the original clip.
- `<end-time>` (_SRT time_): End time of the cut in the original clip.

Supports comments with `#` characters and fields separation by any number of spaces or tabs.

##### _SRT time_

```srt
# <hours>:<minutes>:<seconds>(,<microseconds>)? (eg. 01:02:03,456)
\d+:\d+:\d+(\,\d+)
```

##### Example

```txt
# This is a comment
1
00:00:01,000 --> 00:00:03,000  # hours:minutes:seconds,microseconds

2
00:00:01,600 --> 00:00:04,200

1
00:00:03,000 --> 00:00:05,000

2
00:05:04,100 --> 00:06:07,300
```

### Properties

When you click on `Add` -> `Text to sequences`, the file browser will display a menu at the side with options to customize the generation of the new timeline of sequences.

- <a href="#property-select_new_sequences">#</a> **Select new sequences** (_enabled_): Select the new generated sequences after creating them.
- <a href="#property-select_original_sequences">#</a> **Select original sequences**: Select the original sequences after creating the new ones.
- <a href="#property-mute_new_sequences">#</a> **Mute new sequences**: Mute channels of new sequences after creating them.
- <a href="#property-mute_original_sequences">#</a> **Mute original sequences**: Mute channels of original sequences after creating the new ones.
