"""Encode the actual screen capture and local narration into a 60-second MP4.

Requires ffmpeg on PATH, or the optional imageio-ffmpeg installation under
.tools/video. Audio segments are synthesized locally with macOS `say`; this
recording is the product walkthrough and does not replace the team video.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "submission/walkthrough"
ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    sys.path.insert(0, str(ROOT / ".tools/video"))
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
capture = json.loads((out / "capture.json").read_text())
segments = json.loads((out / "narration.json").read_text())["segments"]
args = [ffmpeg, "-y", "-ss", str(capture["trim_start_seconds"]), "-i", capture["raw_video_path"]]
for i in range(len(segments)):
    args += ["-i", str(ROOT / ".tools/walkthrough-audio" / f"{i}.aiff")]
filters = [f'[{i+1}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=mono,apad,atrim=duration={s["duration_seconds"]},asetpts=PTS-STARTPTS[a{i}]'
           for i, s in enumerate(segments)]
filters.append("".join(f"[a{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=0:a=1,loudnorm=I=-16:LRA=11:TP=-1.5[narration]")
destination = out / "RareBridge-60s-walkthrough.mp4"
args += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[narration]",
         "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-t", "60", str(destination)]
result = subprocess.run(args, capture_output=True, text=True, check=False)
if result.returncode:
    raise SystemExit("Walkthrough encoding failed; inspect local encoder configuration.")
probe = subprocess.run([ffmpeg, "-i", str(destination)], capture_output=True, text=True, check=False)
duration = re.search(r"Duration: ([0-9:.]+)", probe.stderr)
report = {"capture_source": capture["base_url"], "real_public_api": True, "mocked_responses": False,
          "duration": duration.group(1) if duration else None,
          "video_file": destination.relative_to(ROOT).as_posix(), "bytes": destination.stat().st_size,
          "narration": "macOS Samantha synthesized narration", "browser_errors": capture["browser_errors"],
          "events": capture["events"], "purpose": "Separate one-minute product walkthrough; does not replace the team video."}
if report["duration"] != "00:01:00.00" or report["browser_errors"]:
    raise SystemExit("Walkthrough verification failed.")
(out / "VIDEO_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
for t in (12, 29, 49, 55):
    subprocess.run([ffmpeg, "-y", "-ss", str(t), "-i", str(destination), "-frames:v", "1", str(out / f"frame-{t}.png")],
                   capture_output=True, text=True, check=True)
print(json.dumps(report, indent=2))
