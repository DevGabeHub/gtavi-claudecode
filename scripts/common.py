"""Shared helpers: paths, tool lookup, yt-dlp and ffmpeg wrappers."""
import hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(os.environ.get("CLIP_DESK_HOME", Path.cwd()))
JOBS = ROOT / "jobs"


# Full ffmpeg builds that are not on PATH by default (Homebrew installs ffmpeg-full keg-only).
FFMPEG_DIRS = ["/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"]
_ffmpeg_dir = {}


def _has_subtitles(ffmpeg):
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-filters"], text=True, capture_output=True, timeout=20)
    except Exception:
        return False
    return any(line.split()[1:2] == ["subtitles"] for line in r.stdout.splitlines() if line.strip())


def ffmpeg_dir(need_subs=False):
    """Folder of the ffmpeg to use. Prefers a build with libass (the subtitles filter), which burned captions need.

    Order: $FFMPEG_DIR, Homebrew ffmpeg-full, then ffmpeg on PATH. The plain Homebrew `ffmpeg` has no libass.
    """
    if "dir" not in _ffmpeg_dir:
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        cands = [os.environ.get("FFMPEG_DIR")] + FFMPEG_DIRS + [str(Path(p).parent) if (p := shutil.which("ffmpeg")) else None]
        cands = [c for c in dict.fromkeys(cands) if c and (Path(c) / exe).exists()]
        if not cands:
            sys.exit("ffmpeg not found. Run the setup skill first (it installs ffmpeg and yt-dlp).")
        with_subs = next((c for c in cands if _has_subtitles(str(Path(c) / exe))), None)
        _ffmpeg_dir["dir"], _ffmpeg_dir["subs"] = with_subs or cands[0], bool(with_subs)
    if need_subs and not _ffmpeg_dir["subs"]:
        hint = ("brew install ffmpeg-full (the plain `brew install ffmpeg` has no libass)" if sys.platform == "darwin"
                else "install an ffmpeg build with libass, or set FFMPEG_DIR to its folder")
        sys.exit(f"ffmpeg in {_ffmpeg_dir['dir']} has no 'subtitles' filter (libass), so captions cannot be burned in.\n"
                 f"Fix: {hint}. The scripts find it on their own.")
    return _ffmpeg_dir["dir"]


def tool(name, need_subs=False):
    if name in ("ffmpeg", "ffprobe"):
        exe = name + (".exe" if sys.platform == "win32" else "")
        p = Path(ffmpeg_dir(need_subs)) / exe
        if p.exists():
            return str(p)
    p = shutil.which(name)
    if not p:
        sys.exit(f"{name} not found. Run the setup skill first (it installs ffmpeg and yt-dlp).")
    return p


def run(cmd, check=True, capture=False):
    r = subprocess.run(cmd, check=False, text=True, encoding="utf-8", errors="replace",
                       stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    if check and r.returncode != 0:
        msg = (r.stderr or "")[-1500:] if capture else ""
        sys.exit(f"command failed ({r.returncode}): {' '.join(map(str, cmd))[:200]}\n{msg}")
    return r


def ytdlp_base():
    import importlib.util
    exe = [sys.executable, "-m", "yt_dlp"] if importlib.util.find_spec("yt_dlp") else [tool("yt-dlp")]
    base = exe + ["--no-warnings", "--no-progress"]
    if sys.platform == "win32":
        base += ["--compat-options", "no-certifi"]  # use the Windows certificate store
    return base


def ytdlp_json(url, extra=()):
    r = run(ytdlp_base() + ["-J", *extra, url], capture=True)
    return json.loads(r.stdout)


def is_url(s):
    return bool(re.match(r"https?://", s))


def job_dir(src):
    key = hashlib.sha1(src.encode()).hexdigest()[:8]
    stem = re.sub(r"[^a-z0-9]+", "-", Path(src).stem.lower() if not is_url(src) else src.split("v=")[-1].split("/")[-1].lower())[:24].strip("-")
    d = JOBS / f"{stem or 'job'}-{key}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ffprobe(path):
    r = run([tool("ffprobe"), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
             "-of", "json", str(path)], capture=True)
    return json.loads(r.stdout)


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
