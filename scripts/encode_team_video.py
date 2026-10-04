"""Combine real public UI recordings, accepted AI screenshots and team credits.

Local narration uses macOS Samantha, disclosed in the credits and metadata.
No team faces/voices are fabricated. The app data and outputs are never mocked.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "submission/team-video"
tools = ROOT / ".tools/team-encoding"
tools.mkdir(parents=True, exist_ok=True)
content = json.loads((out / "CONTENT.json").read_text())
ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    sys.path.insert(0, str(ROOT / ".tools/video"))
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
governed = json.loads((ROOT / ".tools/governed-capture.json").read_text())
public_ai = json.loads((ROOT / "submission/ai-public-browser-verification/report.json").read_text())
assert public_ai["passed"] and public_ai["base_url"] == content["public_demo_url"]
assert not governed["browser_errors"] and governed["mocked_responses"] is False


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode:
        raise SystemExit("Team video step failed; inspect the local encoder/input configuration.")


images = {
    "intro": ROOT / ".tools/team-cards/intro.png",
    "current_answer": ROOT / "frontend/screenshots/integrated-ai-patient-answer.png",
    "research_scout": ROOT / "frontend/screenshots/integrated-ai-research-leads.png",
    "credits_impact": ROOT / ".tools/team-cards/collaboration_impact.png",
}
clips = []
for i, segment in enumerate(content["segments"]):
    identifier, duration = segment["id"], segment["duration_seconds"]
    destination = tools / f"{i}.mp4"
    args = [ffmpeg, "-y"]
    if identifier == "walkthrough":
        args += ["-i", str(ROOT / segment["visual"])]
    else:
        text_path, audio = tools / f"{i}.txt", tools / f"{i}.aiff"
        text_path.write_text(segment["narration"])
        run(["/usr/bin/say", "-v", "Samantha", "-r", "190", "-f", str(text_path), "-o", str(audio)])
        if identifier == "governed_data":
            args += ["-ss", str(governed["trim_start_seconds"]), "-i", governed["raw_video_path"]]
        else:
            args += ["-loop", "1", "-framerate", "25", "-i", str(images[identifier])]
        args += ["-i", str(audio), "-map", "0:v", "-map", "1:a"]
    args += ["-vf", "scale=1440:1000:force_original_aspect_ratio=decrease,pad=1440:1000:(ow-iw)/2:(oh-ih)/2:color=0x09111f,setsar=1,fps=25",
             "-af", f"aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={duration},loudnorm=I=-16:LRA=11:TP=-1.5",
             "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", str(duration), str(destination)]
    run(args)
    clips.append(destination)
concat = tools / "clips.txt"
concat.write_text("".join("file '" + str(path).replace("'", "'\\''") + "'\n" for path in clips))
destination = out / "RareBridge-team-video.mp4"
run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(destination)])
probe = subprocess.run([ffmpeg, "-i", str(destination)], capture_output=True, text=True, check=False)
duration = re.search(r"Duration: ([0-9:.]+)", probe.stderr)
report = {"video_file": destination.relative_to(ROOT).as_posix(), "duration": duration.group(1) if duration else None,
          "bytes": destination.stat().st_size, "public_app": content["public_demo_url"],
          "source_repository": content["source_repository_url"], "narration": "macOS Samantha synthesized narration",
          "team_credits": content["team_credits"], "real_public_ui_capture": True, "mocked_responses": False,
          "ai_capture_evidence": "submission/ai-public-browser-verification/report.json",
          "ai_provider_results": public_ai["genuine_provider_results"],
          "scope": "Team video using real patient-group workflow, accepted public AI output, governed-access example and truthful credits.",
          "impact": "No measured 10x or treatment milestone acceleration is claimed."}
(out / "VIDEO_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
for seconds in (2, 74, 84, 102, 130):
    run([ffmpeg, "-y", "-ss", str(seconds), "-i", str(destination), "-frames:v", "1", str(out / f"frame-{seconds}.png")])
print(json.dumps(report, indent=2))
