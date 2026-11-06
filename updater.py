# -*- coding: utf-8 -*-
"""
Kiem tra va cap nhat Muse2Tele tu GitHub, GIU NGUYEN du lieu.

  python updater.py check            # in JSON: co ban moi khong
  python updater.py apply [--fox-url URL] [--fox-pid PID] [--no-restart]

Hai kieu cai dat:
  - git:  thu muc co .git -> git fetch + git merge --ff-only (tu choi neu co thay doi chua commit / lech nhanh).
  - zip:  tai ZIP nhanh main tu GitHub, ghi de cac file code. Commit da cai luu o .update/installed.json.
Du lieu khong bao gio bi ghi de / xoa: .env, foxprofile/data/, Videos/, social_post/data|logs/, file trang thai
cua bot, .venv/, .git/, .update/. File code bi ghi de duoc sao luu vao .update/backup/<thoi diem>/.

Khi cap nhat: chuan bi xong (tai/fetch) moi dung dich vu -> dung cac profile qua API FoxProfile -> tat FoxProfile,
bot, AutoPost (tien trinh python co thu muc lam viec trong du an) -> ap dung -> pip install neu requirements doi
-> chay lai start_all.bat -> mo lai cac profile dang chay. Tien trinh: .update/status.json, nhat ky: .update/update.log.
Chi dung thu vien chuan (+ psutil neu co).
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

REPO = os.environ.get("MUSE2TELE_REPO", "vitbau246/Muse2Tele")
BRANCH = os.environ.get("MUSE2TELE_BRANCH", "main")
API = f"https://api.github.com/repos/{REPO}"
ZIP_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
UA = {"User-Agent": "Muse2Tele-updater", "Accept": "application/vnd.github+json"}

# Duong dan (tuong doi, dau /) khong bao gio ghi de / xoa. Ket thuc bang "/" = ca thu muc.
PROTECTED = (
    ".git/", ".venv/", "venv/", ".update/", ".env", "Videos/",
    "foxprofile/data/", "social_post/data/", "social_post/logs/",
    "muse_telebot/muse_telebot_state.json", "muse_telebot/muse_sync.json", "muse_telebot/muse_users.db",
    "muse_telebot/muse_autoapprove.json", "muse_telebot/muse_telebot.log", "muse_telebot/muse_team.json",
)
REQUIREMENTS = ("requirements.txt", "foxprofile/repo/requirements.txt")


def find_root(start: Path | None = None) -> Path | None:
    """Thu muc goc Muse2Tele: noi co updater.py + start_all.bat (tim tu `start` di len)."""
    here = (start or Path(__file__).resolve().parent).resolve()
    for d in (here, *here.parents):
        if (d / "updater.py").is_file() and (d / "start_all.bat").is_file():
            return d
    return None


def protected(rel: str) -> bool:
    rel = rel.replace("\\", "/").lstrip("/")
    return any(rel == p.rstrip("/") or (p.endswith("/") and rel.startswith(p)) or rel == p for p in PROTECTED)


# ---------- GitHub ----------

def _get(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def remote_head() -> dict:
    data = json.loads(_get(f"{API}/commits/{BRANCH}"))
    return {
        "sha": data["sha"],
        "date": data["commit"]["committer"]["date"],
        "message": data["commit"]["message"].splitlines()[0][:200],
    }


def changes_between(base: str, head: str, limit: int = 15) -> list[str]:
    """Tieu de cac commit tu base toi head (moi nhat truoc)."""
    try:
        data = json.loads(_get(f"{API}/compare/{base}...{head}"))
    except (urllib.error.URLError, ValueError, OSError):
        return []
    msgs = [c["commit"]["message"].splitlines()[0][:150] for c in data.get("commits", [])]
    return [m for m in reversed(msgs) if not m.startswith("Merge ")][:limit]


# ---------- Ban dang cai ----------

def _git(root: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_git(root: Path) -> bool:
    if not (root / ".git").exists() or not shutil.which("git"):
        return False
    try:
        return Path(_git(root, "rev-parse", "--show-toplevel")).resolve() == root.resolve()
    except (RuntimeError, OSError):
        return False


def _is_ancestor(root: Path, older: str, newer: str) -> bool:
    return subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", older, newer],
                          capture_output=True, creationflags=_NO_WINDOW).returncode == 0


def installed_file(root: Path) -> Path:
    return root / ".update" / "installed.json"


def local_info(root: Path) -> dict:
    if is_git(root):
        return {"mode": "git", "sha": _git(root, "rev-parse", "HEAD"),
                "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD")}
    try:
        data = json.loads(installed_file(root).read_text(encoding="utf-8"))
        return {"mode": "zip", "sha": data.get("sha"), "installed_at": data.get("installed_at")}
    except (OSError, ValueError):
        return {"mode": "zip", "sha": None}


def check(root: Path) -> dict:
    """{available, mode, local_sha, remote: {...}, changes: [...], error, note}."""
    out = {"available": False, "repo": REPO, "branch": BRANCH, "checked_at": datetime.now().isoformat(timespec="seconds")}
    try:
        local = local_info(root)
        out.update(mode=local["mode"], local_sha=local["sha"])
        remote = remote_head()
        out["remote"] = remote
        if local["sha"] == remote["sha"]:
            return out
        if local["mode"] == "git":
            try:
                _git(root, "fetch", "--quiet", "origin", BRANCH)
                if _is_ancestor(root, remote["sha"], "HEAD"):
                    return out  # ban local da chua commit moi nhat (dang phat trien, di truoc)
            except RuntimeError as e:
                out["note"] = str(e)
        out["available"] = True
        if local["sha"]:
            out["changes"] = changes_between(local["sha"], remote["sha"])
        else:
            out["note"] = "Chưa biết bản đang cài (bản tải ZIP): cập nhật 1 lần để đồng bộ."
    except (urllib.error.URLError, OSError, ValueError, KeyError, RuntimeError) as e:
        out["error"] = f"Không kiểm tra được phiên bản mới: {e}"
    return out


# ---------- Thanh phan dang chay ----------

# Thanh phan -> (doan cuoi tham so dong lenh, thu muc lam viec tuong doi so voi goc du an)
COMPONENTS = {
    "foxprofile": ("main.py", "foxprofile/data"),
    "bot": ("muse_telebot.py", "muse_telebot"),
    "autopost": ("auto_post.py", "social_post"),
}
# Tac vu Task Scheduler cua watchdog (apps_monitor) tu mo lai thanh phan khi no chet, neu may co cai.
MANAGED_TASKS = {"foxprofile": "Muse2tele_FoxProfile", "bot": "Muse2tele_Bot", "autopost": "Muse2tele_AutoPost"}


def component_running(root: Path, name: str) -> bool:
    try:
        import psutil
    except ImportError:
        return False
    arg, cwd_rel = COMPONENTS[name]
    want = os.path.normcase(str((root / cwd_rel).resolve()))
    for p in psutil.process_iter(["name", "cmdline", "cwd"]):
        try:
            if not (p.info["name"] or "").lower().startswith("python") or p.pid == os.getpid():
                continue
            args = p.info["cmdline"] or []
            if any(a.lower().endswith(arg) for a in args[1:]) and os.path.normcase(p.info["cwd"] or "") == want:
                return True
        except (psutil.Error, OSError):
            continue
    return False


def task_exists(name: str) -> bool:
    if os.name != "nt":
        return False
    return subprocess.run(["schtasks", "/query", "/tn", name], capture_output=True,
                          creationflags=_NO_WINDOW).returncode == 0


# ---------- Ap dung ----------

class Updater:
    def __init__(self, root: Path, fox_url: str, fox_pid: int | None, restart: bool):
        self.root = root
        self.fox_url = fox_url.rstrip("/")
        self.fox_pid = fox_pid
        self.restart = restart
        self.dir = root / ".update"
        self.dir.mkdir(exist_ok=True)
        self.stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.status_path = self.dir / "status.json"

    # -- nhat ky / trang thai --
    def log(self, msg: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        try:  # chay tach roi thi khong co console; console cp1252 khong in duoc tieng Viet
            print(line, flush=True)
        except (OSError, ValueError, UnicodeError, AttributeError):
            pass
        with (self.dir / "update.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def status(self, state: str, message: str, **extra) -> None:
        data = {"state": state, "message": message, "at": datetime.now().isoformat(timespec="seconds"), **extra}
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.status_path)
        self.log(f"[{state}] {message}")

    # -- FoxProfile API --
    def _api(self, method: str, path: str, timeout: float = 60):
        req = urllib.request.Request(f"{self.fox_url}/api/v1{path}", method=method, headers={"Content-Type": "application/json"})
        token = os.environ.get("FOXPROFILE_API_TOKEN", "")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        if method == "POST":
            req.data = b"{}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")

    def running_profiles(self) -> list[str]:
        try:
            return [p["name"] for p in self._api("GET", "/profiles", 15)["profiles"] if p.get("is_running")]
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return []

    # -- buoc 1: chuan bi (chua dung gi) --
    def prepare(self, info: dict):
        mode = info["mode"]
        if mode == "git":
            branch = _git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
            if branch != BRANCH:
                raise RuntimeError(f"Đang ở nhánh '{branch}', chỉ tự cập nhật nhánh '{BRANCH}'.")
            dirty = _git(self.root, "status", "--porcelain", "--untracked-files=no")
            if dirty:
                files = ", ".join(line[3:] for line in dirty.splitlines()[:8])
                raise RuntimeError(f"Có thay đổi chưa commit ({files}). Commit hoặc huỷ chúng rồi cập nhật lại.")
            _git(self.root, "fetch", "--quiet", "origin", BRANCH)
            if not _is_ancestor(self.root, "HEAD", f"origin/{BRANCH}"):
                raise RuntimeError("Bản local đã lệch khỏi GitHub (có commit riêng), không thể cập nhật tự động.")
            return None
        self.log(f"Tai {ZIP_URL}")
        data = _get(ZIP_URL, timeout=300)
        zf = zipfile.ZipFile(io.BytesIO(data))
        sha = (zf.comment or b"").decode("ascii", "ignore").strip() or info["remote"]["sha"]
        top = zf.namelist()[0].split("/")[0] + "/"
        files = {}
        for name in zf.namelist():
            if name.endswith("/") or not name.startswith(top):
                continue
            rel = name[len(top):]
            if rel and not protected(rel):
                files[rel] = zf.read(name)
        if "start_all.bat" not in files or "updater.py" not in files:
            raise RuntimeError("File ZIP tải về không giống bản Muse2Tele, dừng cập nhật.")
        self.log(f"Da tai {len(files)} file (commit {sha[:10]})")
        return {"sha": sha, "files": files}

    # -- buoc 2: dung dich vu --
    def stop_services(self) -> list[str]:
        running = self.running_profiles()
        for name in running:
            try:
                self._api("POST", f"/browser/{urllib.request.quote(name, safe='')}/stop", 90)
                self.log(f"Da dung profile {name}")
            except (urllib.error.URLError, OSError) as e:
                self.log(f"Khong dung duoc profile {name}: {e}")
        self.kill_processes()
        return running

    def kill_processes(self) -> None:
        """Tat FoxProfile, bot, AutoPost: tien trinh python co thu muc lam viec trong du an + cua so cmd chay start_*.bat."""
        try:
            import psutil
        except ImportError:
            self.log("Thieu psutil: chi tat duoc FoxProfile theo PID")
            if self.fox_pid:
                subprocess.run(["taskkill", "/PID", str(self.fox_pid), "/T", "/F"], capture_output=True)
            return
        me = {os.getpid()}  # chay tach roi (DETACHED): tat FoxProfile - tien trinh cha - khong keo theo updater
        root = str(self.root).lower()
        victims = []
        for p in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
            if p.info["pid"] in me:
                continue
            try:
                name = (p.info["name"] or "").lower()
                cmd = " ".join(p.info["cmdline"] or []).lower()
                cwd = (p.info["cwd"] or "").lower()
            except (psutil.Error, OSError):
                continue
            if name.startswith("python") and (cwd.startswith(root) or root in cmd):
                victims.append(p)
            elif name == "cmd.exe" and root in cmd and "start_" in cmd and "updater" not in cmd:
                victims.append(p)
        if self.fox_pid and self.fox_pid not in me:
            try:
                victims.append(psutil.Process(self.fox_pid))
            except psutil.Error:
                pass
        for p in victims:
            try:
                for c in p.children(recursive=True):
                    if c.pid not in me:
                        c.kill()
                p.kill()
                self.log(f"Da tat tien trinh {p.pid}")
            except psutil.Error:
                pass
        psutil.wait_procs([p for p in victims if p.is_running()], timeout=10)
        time.sleep(2)  # Windows nha file

    # -- buoc 3: ap dung --
    def _req_hash(self) -> str:
        h = hashlib.sha256()
        for rel in REQUIREMENTS:
            p = self.root / rel
            h.update(p.read_bytes() if p.is_file() else b"-")
        return h.hexdigest()

    def apply_git(self) -> str:
        _git(self.root, "merge", "--ff-only", f"origin/{BRANCH}")
        return _git(self.root, "rev-parse", "HEAD")

    def apply_zip(self, prepared: dict) -> str:
        files: dict[str, bytes] = prepared["files"]
        backup = self.dir / "backup" / self.stamp
        manifest_path = self.dir / "manifest.json"
        try:
            old = set(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            old = set()
        changed = 0
        for rel, data in files.items():
            dest = self.root / rel
            if dest.is_file():
                if dest.read_bytes() == data:
                    continue
                (backup / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup / rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".update-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            changed += 1
        removed = 0
        for rel in sorted(old - set(files)):  # file da bi xoa tren GitHub (chi xoa file do updater cai)
            dest = self.root / rel
            if dest.is_file() and not protected(rel):
                (backup / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest), str(backup / rel))
                removed += 1
        manifest_path.write_text(json.dumps(sorted(files), indent=0), encoding="utf-8")
        self.log(f"Ghi {changed} file, xoa {removed} file cu" + (f", sao luu o {backup}" if backup.exists() else ""))
        self._prune_backups()
        return prepared["sha"]

    def _prune_backups(self, keep: int = 3) -> None:
        root = self.dir / "backup"
        if root.is_dir():
            for old in sorted(p for p in root.iterdir() if p.is_dir())[:-keep]:
                shutil.rmtree(old, ignore_errors=True)

    def pip_install(self) -> None:
        for rel in ("requirements.txt",):
            self.log(f"Cai thu vien: pip install -r {rel}")
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", rel], cwd=self.root,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.log((r.stdout + r.stderr).strip()[-1500:])

    # -- buoc 4: khoi dong lai --
    def start_services(self, profiles: list[str]) -> None:
        # May co watchdog (Task Scheduler + apps_monitor) thi no tu mo lai cac thanh phan co tac vu: cho no, khong
        # mo them ban trung. Thanh phan nao van chua chay (khong co tac vu / watchdog tat) thi start_all.bat mo.
        managed = [c for c, task in MANAGED_TASKS.items() if task_exists(task)]
        if managed:
            self.log(f"Watchdog quan ly {managed}: cho no mo lai (toi da 120s)")
            deadline = time.time() + 120
            while time.time() < deadline and not all(component_running(self.root, c) for c in managed):
                time.sleep(3)
        if not all(component_running(self.root, c) for c in COMPONENTS):
            bat = self.root / "start_all.bat"
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(["cmd.exe", "/c", str(bat)], cwd=self.root, creationflags=flags, close_fds=True)
            self.log("Da chay start_all.bat (chi mo thanh phan chua chay), cho FoxProfile san sang...")
        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                self._api("GET", "/health", 5)
                break
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(3)
        else:
            self.log("FoxProfile chua len sau 5 phut, bo qua viec mo lai profile")
            return
        for name in profiles:
            try:
                self._api("POST", f"/browser/{urllib.request.quote(name, safe='')}/launch", 240)
                self.log(f"Da mo lai profile {name}")
            except (urllib.error.URLError, OSError) as e:
                self.log(f"Khong mo lai duoc profile {name}: {e}")

    def run(self) -> int:
        self.status("checking", "Đang kiểm tra phiên bản mới...")
        info = check(self.root)
        if info.get("error"):
            self.status("error", info["error"])
            return 1
        if not info["available"]:
            self.status("done", "Đang dùng phiên bản mới nhất.", sha=info.get("local_sha"))
            return 0
        try:
            self.status("preparing", "Đang tải bản mới...")
            prepared = self.prepare(info)
        except Exception as e:
            self.status("error", f"Chưa cập nhật (chưa tắt gì): {e}")
            return 1
        before = self._req_hash()
        self.status("stopping", "Đang dừng profile, FoxProfile, bot và AutoPost...")
        profiles = self.stop_services()
        try:
            self.status("applying", "Đang cập nhật code (dữ liệu giữ nguyên)...")
            sha = self.apply_git() if info["mode"] == "git" else self.apply_zip(prepared)
            installed_file(self.root).write_text(json.dumps(
                {"sha": sha, "installed_at": datetime.now().isoformat(timespec="seconds"), "mode": info["mode"]},
                indent=2), encoding="utf-8")
            if self._req_hash() != before:
                self.status("installing", "Đang cài thư viện mới...")
                self.pip_install()
            message = f"Đã cập nhật lên {sha[:7]} ({info['remote']['message']})."
            ok = True
        except Exception as e:
            self.log(f"LOI: {e!r}")
            message, ok, sha = (f"Cập nhật lỗi: {e}. File code cũ được sao lưu trong .update/backup/{self.stamp}.",
                                False, info.get("local_sha"))
        if self.restart:
            self.status("restarting", message + " Đang khởi động lại...")
            self.start_services(profiles)
        self.status("done" if ok else "error", message, sha=sha, profiles=profiles)
        return 0 if ok else 1


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Kiem tra / cap nhat Muse2Tele tu GitHub, giu nguyen du lieu")
    ap.add_argument("action", choices=["check", "apply", "running"])
    ap.add_argument("component", nargs="?", choices=sorted(COMPONENTS),
                    help="running: ma thoat 0 neu thanh phan nay dang chay (dung trong start_*.bat)")
    ap.add_argument("--root", default=None, help="Thu muc Muse2Tele (mac dinh: noi chua updater.py)")
    ap.add_argument("--fox-url", default=os.environ.get("FOXPROFILE_URL", "http://127.0.0.1:8090"))
    ap.add_argument("--fox-pid", type=int, default=None, help="PID FoxProfile can tat")
    ap.add_argument("--no-restart", action="store_true", help="Khong chay lai start_all.bat sau khi cap nhat")
    a = ap.parse_args()
    root = Path(a.root).resolve() if a.root else find_root()
    if not root:
        raise SystemExit("Khong tim thay thu muc Muse2Tele (can updater.py + start_all.bat)")
    if a.action == "check":
        print(json.dumps(check(root), ensure_ascii=False, indent=2))
        return
    if a.action == "running":
        if not a.component:
            ap.error("running can ten thanh phan: " + ", ".join(sorted(COMPONENTS)))
        sys.exit(0 if component_running(root, a.component) else 1)
    sys.exit(Updater(root, a.fox_url, a.fox_pid, not a.no_restart).run())


if __name__ == "__main__":
    main()
