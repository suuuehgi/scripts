#!/usr/bin/env python3
"""Importiert Dateien und Verzeichnisse aus HOME in ein GNU-Stow-Paket.

Sicherheit und Metadaten:
- Neue Stow-Verzeichnisse werden mit Modus 0700 angelegt; bestehende dürfen
  keine Gruppen-/Andere-Bits setzen (geprüft werden nur Unix-Modusbits, keine ACLs).
- Verschieben nutzt os.rename und weicht nur bei EXDEV auf Kopieren + Löschen aus.
  Dabei bleiben Inhalte, Symlinks und übliche Dateimodi erhalten, jedoch ohne
  Garantie für Eigentümer, Gruppe, ACLs, Hardlinks oder Spezialattribute.
"""
from __future__ import annotations

import argparse
import errno
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PKG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\Z")

HELP_TEXT = """\
Nutzung: stowy <pfad> <paket>

Verschiebt <pfad> aus HOME nach $STOW_DIR/<paket> (Standard: ~/dotfiles)
und verlinkt das Paket per 'stow --no-folding' zurück.

Hinweise:
- Das Stow-Verzeichnis darf keine Gruppen-/Andere-Rechte haben (0700;
  geprüft werden nur Unix-Modusbits, keine ACLs).
- Fällt os.rename wegen EXDEV (z. B. Dateisystemgrenze, Bind-Mount) auf
  Kopieren + Löschen zurück, werden Inhalte und übliche Dateimodi übernommen,
  aber keine vollständige Erhaltung von Eigentümer, Gruppe, ACLs, Hardlinks
  oder sonstigen Metadaten garantiert."""


def reconfigure_stderr() -> None:
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(errors="backslashreplace")
        except Exception:
            pass


def fail(msg: str) -> NoReturn:
    reconfigure_stderr()
    print(f"Fehler: {msg}", file=sys.stderr)
    sys.exit(1)


def os_err(exc: OSError) -> str:
    return exc.strerror or str(exc)


def format_reason(exc: BaseException) -> str:
    if isinstance(exc, KeyboardInterrupt):
        return "Vorgang abgebrochen"
    if isinstance(exc, OSError):
        detail = os_err(exc)
        if exc.filename:
            return f"Dateisystemfehler bei '{exc.filename}': {detail}"
        return f"Systemfehler: {detail}"
    return str(exc) or exc.__class__.__name__


def path_present(p: Path) -> bool:
    try:
        os.lstat(p)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


def first_missing_ancestor(path: Path) -> Path | None:
    missing: Path | None = None
    cur = path
    while not path_present(cur):
        missing = cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return missing


def cleanup_parents(start: Path, stop: Path) -> None:
    cur = start
    while cur != stop and cur.is_relative_to(stop):
        try:
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent


def cleanup_created(leaf: Path, first_missing: Path | None) -> None:
    if first_missing is not None:
        cleanup_parents(leaf, first_missing.parent)


def mkdir_secure_parents(target: Path) -> Path | None:
    missing: list[Path] = []
    cur = target
    while not path_present(cur):
        missing.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    created: list[Path] = []
    try:
        for directory in reversed(missing):
            os.mkdir(directory, 0o700)
            created.append(directory)
    except OSError:
        for directory in reversed(created):
            try:
                directory.rmdir()
            except OSError:
                break
        raise
    return created[0] if created else None


def check_stow_ancestor(path: Path, raw_label: Path | str) -> os.stat_result:
    probe = path
    while not path_present(probe):
        if probe.parent == probe:
            break
        probe = probe.parent
    try:
        st_probe = os.stat(probe)
    except OSError as e:
        fail(f"Stow-Verzeichnis '{raw_label}' nicht nutzbar: {os_err(e)}")
    if not stat.S_ISDIR(st_probe.st_mode):
        fail(
            f"Stow-Verzeichnis '{raw_label}' nicht nutzbar: "
            f"'{probe}' ist kein Verzeichnis."
        )
    return st_probe


def verify_stow_dir_mode(abs_stow: Path) -> None:
    try:
        st_dir = os.lstat(abs_stow)
    except OSError as e:
        fail(f"Stow-Verzeichnis '{abs_stow}' nicht prüfbar: {os_err(e)}")
    if not stat.S_ISDIR(st_dir.st_mode):
        fail(f"Stow-Verzeichnis '{abs_stow}' ist kein echtes Verzeichnis.")
    mode = stat.S_IMODE(st_dir.st_mode)
    if mode & 0o077:
        fail(
            f"Stow-Verzeichnis '{abs_stow}' erlaubt Zugriff für Gruppe/Andere "
            f"(Unix-Modus {mode:04o}; ACLs werden nicht geprüft). "
            f"Bitte Rechte manuell einschränken, z. B.: chmod 700 '{abs_stow}'"
        )


def is_link_to_dest(link_path: Path, expected_dest: Path) -> bool:
    try:
        st_link = os.lstat(link_path)
        if not stat.S_ISLNK(st_link.st_mode):
            return False
        raw_target = os.readlink(link_path)
        hop = os.path.join(os.fspath(link_path.parent), raw_target)
        return os.path.samestat(os.lstat(hop), os.lstat(expected_dest))
    except OSError:
        return False


def chmod_real_dir(path: Path, mode: int) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise RuntimeError(f"'{path}' ist kein echtes Verzeichnis")
        if stat.S_IMODE(st.st_mode) != mode:
            os.fchmod(fd, mode)
    finally:
        os.close(fd)


def restore_dir_modes(abs_src: Path, dir_modes: list[tuple[Path, int]]) -> None:
    for rel_dir, mode in reversed(dir_modes):
        target = abs_src / rel_dir
        try:
            chmod_real_dir(target, mode)
        except OSError as e:
            raise RuntimeError(
                f"Verzeichnisrechte ({oct(mode)}) für '{target}' konnten "
                f"nicht wiederhergestellt werden: {os_err(e)}"
            ) from e


def check_source_parents(cleaned_src: str, abs_home: Path) -> None:
    raw_path = Path(cleaned_src)
    if not raw_path.is_absolute():
        try:
            raw_path = Path.cwd() / raw_path
        except OSError as e:
            fail(f"Arbeitsverzeichnis nicht ermittelbar: {os_err(e)}")

    cur = Path("/")
    inside_home = False
    parts = raw_path.parts[1:]
    for idx, part in enumerate(parts):
        is_last = idx == len(parts) - 1
        if part in ("", "."):
            continue
        if part == "..":
            cur = cur.parent
            if inside_home and not cur.is_relative_to(abs_home):
                inside_home = False
            if not inside_home and cur == abs_home:
                inside_home = True
            continue

        cur = cur / part
        try:
            st_part = os.lstat(cur)
        except OSError as e:
            fail(f"Zugriff auf '{cur}' fehlgeschlagen: {os_err(e)}")

        if inside_home:
            if stat.S_ISLNK(st_part.st_mode):
                if is_last:
                    fail(f"'{cleaned_src}' ist bereits ein Symlink.")
                fail(f"Übergeordnetes Verzeichnis '{cur}' ist ein Symlink.")
        else:
            if is_last and stat.S_ISLNK(st_part.st_mode):
                fail(f"'{cleaned_src}' ist bereits ein Symlink.")
            try:
                cur = cur.resolve(strict=True)
            except (OSError, RuntimeError) as e:
                fail(f"Pfadauflösung bei '{cur}' fehlgeschlagen: {format_reason(e)}")
            if cur == abs_home:
                inside_home = True

    if not inside_home:
        fail(
            f"Pfad '{cleaned_src}' verläuft über einen Symlink, "
            f"der '{abs_home}' umgeht."
        )


def validate_inner_symlink(link_path: Path, abs_stow: Path) -> None:
    try:
        raw_target = os.readlink(link_path)
    except OSError as e:
        fail(f"Symlink '{link_path}' nicht lesbar: {os_err(e)}")

    try:
        resolved = link_path.resolve(strict=False)
        in_stow = resolved.is_relative_to(abs_stow)
    except (OSError, RuntimeError):
        in_stow = (
            os.path.isabs(raw_target)
            and Path(raw_target).is_relative_to(abs_stow)
        )

    if in_stow:
        fail(
            f"Symlink '{link_path}' zeigt bereits in das "
            f"Stow-Verzeichnis '{abs_stow}'."
        )

    if not os.path.isabs(raw_target):
        fail(
            f"Relativer Symlink '{link_path}' -> '{raw_target}' wird nicht "
            f"unterstützt (Ziel würde sich durch das Verschieben ändern)."
        )


def validate_source_dir(
    root: Path, abs_stow: Path, cross_device: bool
) -> list[tuple[Path, int]]:
    dir_modes: list[tuple[Path, int]] = []
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            st_cur = os.lstat(cur)
        except OSError as e:
            fail(f"Zugriff auf '{cur}' fehlgeschlagen: {os_err(e)}")
        if not stat.S_ISDIR(st_cur.st_mode):
            fail(f"'{cur}' ist kein echtes Verzeichnis.")
        if os.path.ismount(cur):
            fail(
                f"'{cur}' ist ein Einhängepunkt (Mountpoint) "
                f"und kann nicht verschoben werden."
            )
        if cross_device and not os.access(cur, os.W_OK | os.X_OK):
            fail(
                f"Verzeichnis '{cur}' ist nicht beschreibbar "
                f"(für dateisystemübergreifendes Verschieben erforderlich)."
            )
        dir_modes.append((cur.relative_to(root), stat.S_IMODE(st_cur.st_mode)))

        try:
            with os.scandir(cur) as it:
                entries = list(it)
        except OSError as e:
            fail(f"Keine Zugriffsrechte für '{cur}': {os_err(e)}")
        if not entries:
            fail(
                f"Verzeichnis '{cur}' ist leer "
                f"('stow --no-folding' legt keine leeren Ordner an)."
            )
        for entry in entries:
            entry_path = Path(entry.path)
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as e:
                fail(f"Zugriff auf '{entry.path}' fehlgeschlagen: {os_err(e)}")
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                stack.append(entry_path)
            elif stat.S_ISLNK(mode):
                validate_inner_symlink(entry_path, abs_stow)
            elif stat.S_ISREG(mode):
                if cross_device and not os.access(entry_path, os.R_OK):
                    fail(
                        f"Datei '{entry.path}' ist nicht lesbar "
                        f"(für dateisystemübergreifendes Verschieben erforderlich)."
                    )
            else:
                fail(
                    f"'{entry.path}' ist ein Spezialdateityp (nur reguläre "
                    f"Dateien, Ordner und absolute Symlinks erlaubt)."
                )
    return dir_modes


def ensure_copy_permissions(src: Path, is_dir: bool) -> None:
    if not is_dir:
        if not os.access(src, os.R_OK):
            raise PermissionError(
                errno.EACCES,
                "Datei ist nicht lesbar (für Kopier-Fallback erforderlich)",
                os.fspath(src),
            )
        return

    stack = [src]
    while stack:
        cur = stack.pop()
        if not os.access(cur, os.W_OK | os.X_OK):
            raise PermissionError(
                errno.EACCES,
                "Verzeichnis ist nicht beschreibbar (für Kopier-Fallback erforderlich)",
                os.fspath(cur),
            )
        with os.scandir(cur) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    if not os.access(entry.path, os.R_OK):
                        raise PermissionError(
                            errno.EACCES,
                            "Datei ist nicht lesbar (für Kopier-Fallback erforderlich)",
                            entry.path,
                        )


def move_path(src: Path, dst: Path, is_dir: bool, copy_checked: bool) -> None:
    try:
        os.rename(src, dst)
        return
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise

    if not copy_checked:
        ensure_copy_permissions(src, is_dir)
    if path_present(dst):
        raise FileExistsError(
            errno.EEXIST, "Ziel existiert bereits", os.fspath(dst)
        )
    shutil.move(os.fspath(src), os.fspath(dst))


def verify_stowed_tree(dest: Path, abs_src: Path, is_dir: bool) -> None:
    if not is_dir:
        if not is_link_to_dest(abs_src, dest):
            raise RuntimeError(
                f"Symlink '{abs_src}' fehlt oder zeigt nicht auf '{dest}' "
                f"(z. B. Stow-Ignore)"
            )
        return

    try:
        st_root = os.lstat(abs_src)
    except OSError as e:
        raise RuntimeError(
            f"Zielverzeichnis '{abs_src}' wurde nicht angelegt"
        ) from e
    if not stat.S_ISDIR(st_root.st_mode):
        raise RuntimeError(f"'{abs_src}' ist kein echtes Verzeichnis")

    stack = [Path(".")]
    while stack:
        rel_dir = stack.pop()
        dest_dir = dest / rel_dir
        try:
            with os.scandir(dest_dir) as it:
                entries = list(it)
        except OSError as e:
            raise RuntimeError(
                f"Verifikation von '{dest_dir}' fehlgeschlagen: {os_err(e)}"
            ) from e

        for entry in entries:
            rel_item = rel_dir / entry.name
            dest_item = dest / rel_item
            src_item = abs_src / rel_item
            try:
                entry_is_dir = entry.is_dir(follow_symlinks=False)
            except OSError as e:
                raise RuntimeError(
                    f"Verifikation von '{dest_item}' fehlgeschlagen: {os_err(e)}"
                ) from e

            if entry_is_dir:
                try:
                    st_sub = os.lstat(src_item)
                except OSError as e:
                    raise RuntimeError(
                        f"Ordner '{src_item}' wurde von Stow übersprungen "
                        f"(z. B. Stow-Ignore)"
                    ) from e
                if not stat.S_ISDIR(st_sub.st_mode):
                    raise RuntimeError(
                        f"'{src_item}' ist kein echtes Verzeichnis"
                    )
                stack.append(rel_item)
            elif not is_link_to_dest(src_item, dest_item):
                raise RuntimeError(
                    f"Eintrag '{src_item}' wurde von Stow nicht verlinkt "
                    f"(z. B. Stow-Ignore)"
                )


def cleanup_partial_stow(abs_src: Path, dest: Path, is_dir: bool) -> bool:
    try:
        st = os.lstat(abs_src)
    except FileNotFoundError:
        return True
    except OSError:
        return False

    if not is_dir:
        if not is_link_to_dest(abs_src, dest):
            return False
        try:
            abs_src.unlink()
            return True
        except OSError:
            return False

    if not stat.S_ISDIR(st.st_mode):
        return False

    dirs_to_remove: list[Path] = [abs_src]
    links_to_remove: list[Path] = []
    stack: list[Path] = [Path(".")]

    try:
        while stack:
            rel_dir = stack.pop()
            src_dir = abs_src / rel_dir
            with os.scandir(src_dir) as it:
                for entry in it:
                    rel_item = rel_dir / entry.name
                    src_item = abs_src / rel_item
                    dest_item = dest / rel_item
                    if entry.is_symlink():
                        if not is_link_to_dest(src_item, dest_item):
                            return False
                        links_to_remove.append(src_item)
                    elif entry.is_dir(follow_symlinks=False):
                        st_dest = os.lstat(dest_item)
                        if not stat.S_ISDIR(st_dest.st_mode):
                            return False
                        dirs_to_remove.append(src_item)
                        stack.append(rel_item)
                    else:
                        return False

        for d in dirs_to_remove:
            st_d = os.lstat(d)
            if (st_d.st_mode & stat.S_IRWXU) != stat.S_IRWXU:
                chmod_real_dir(d, stat.S_IMODE(st_d.st_mode) | stat.S_IRWXU)
        for link in links_to_remove:
            link.unlink()
        for d in reversed(dirs_to_remove):
            d.rmdir()
    except (OSError, RuntimeError):
        return False

    return True


def main() -> None:
    reconfigure_stderr()

    parser = argparse.ArgumentParser(
            description=(
                "Importiert Dateien oder Verzeichnisse aus HOME in ein GNU-Stow-Paket."
            )
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Stow-Ausgabe anzeigen; wiederholbar bis -vvvvv (Level 5).",
    )
    parser.add_argument("path", help="Zu importierende Datei oder Verzeichnis.")
    parser.add_argument("package", help="Name des Stow-Pakets.")
    args = parser.parse_args()
    
    if args.verbose > 5:
        print(
            f"Warnung: Verbosity-Level {args.verbose} auf 5 begrenzt.",
            file=sys.stderr,
        )
        args.verbose = 5

    raw_src = args.path
    pkg = args.package

    home_env = os.environ.get("HOME", "")
    if not home_env:
        fail("HOME ist nicht gesetzt.")

    if shutil.which("stow") is None:
        fail("'stow' nicht gefunden.")

    if not raw_src:
        fail("Leerer Quellpfad.")

    if not PKG_PATTERN.fullmatch(pkg):
        fail(
            f"Ungültiger Paketname '{pkg}' "
            f"(erlaubt: A-Z, a-z, 0-9, '.', '_', '+', '-'; Start mit Buchstabe/Ziffer)."
        )

    has_trailing_slash = len(raw_src) > 1 and raw_src.endswith("/")
    cleaned_src = raw_src.rstrip("/") or "/"
    try:
        st = os.lstat(cleaned_src)
    except FileNotFoundError:
        fail(f"'{cleaned_src}' existiert nicht.")
    except OSError as e:
        fail(f"Zugriff auf '{cleaned_src}' fehlgeschlagen: {os_err(e)}")

    if stat.S_ISLNK(st.st_mode):
        fail(f"'{cleaned_src}' ist bereits ein Symlink.")

    is_dir = stat.S_ISDIR(st.st_mode)
    if has_trailing_slash and not is_dir:
        fail(f"'{raw_src}' endet mit '/', ist aber kein Verzeichnis.")
    if not is_dir and not stat.S_ISREG(st.st_mode):
        fail(f"'{cleaned_src}' ist weder reguläre Datei noch Verzeichnis.")

    try:
        st_home = os.stat(home_env)
        if not stat.S_ISDIR(st_home.st_mode):
            fail(f"HOME ('{home_env}') ist kein Verzeichnis.")
        abs_home = Path(home_env).resolve(strict=True)
        abs_src = Path(cleaned_src).resolve(strict=True)
    except (OSError, RuntimeError) as e:
        fail(f"Pfadauflösung fehlgeschlagen: {format_reason(e)}")

    if abs_home == Path("/"):
        fail("HOME darf nicht '/' sein.")

    if abs_src == abs_home or not abs_src.is_relative_to(abs_home):
        fail(f"'{abs_src}' liegt nicht innerhalb von '{abs_home}'.")

    check_source_parents(cleaned_src, abs_home)

    if os.path.ismount(abs_src):
        fail(
            f"'{abs_src}' ist ein Einhängepunkt (Mountpoint) "
            f"und kann nicht verschoben werden."
        )

    if not os.access(abs_src.parent, os.W_OK | os.X_OK):
        fail(f"Keine Schreibrechte im Verzeichnis '{abs_src.parent}'.")

    stow_env = os.environ.get("STOW_DIR", "")
    stow_label: Path | str = stow_env or (abs_home / "dotfiles")
    try:
        stow_raw = (
            Path(stow_env).expanduser() if stow_env else abs_home / "dotfiles"
        )
        if not stow_raw.is_absolute():
            stow_raw = Path.cwd() / stow_raw
        abs_stow = stow_raw.resolve(strict=False)
        st_src_parent = os.lstat(abs_src.parent)
    except (OSError, RuntimeError) as e:
        fail(f"Stow-Verzeichnis '{stow_label}' nicht nutzbar: {format_reason(e)}")

    if abs_stow == Path("/") or abs_home.is_relative_to(abs_stow):
        fail(f"Ungültiges Stow-Verzeichnis '{abs_stow}'.")

    if abs_src.is_relative_to(abs_stow):
        fail(f"'{abs_src}' liegt bereits im Stow-Verzeichnis.")

    if abs_stow.is_relative_to(abs_src):
        fail(f"'{abs_src}' enthält das Stow-Verzeichnis '{abs_stow}'.")

    check_stow_ancestor(stow_raw, stow_raw)
    st_stow = check_stow_ancestor(abs_stow, stow_raw)
    if path_present(abs_stow):
        verify_stow_dir_mode(abs_stow)

    cross_device = st_src_parent.st_dev != st_stow.st_dev
    dir_modes: list[tuple[Path, int]] = []
    if is_dir:
        dir_modes = validate_source_dir(abs_src, abs_stow, cross_device)
    elif cross_device and not os.access(abs_src, os.R_OK):
        fail(
            f"Datei '{abs_src}' ist nicht lesbar "
            f"(für dateisystemübergreifendes Verschieben erforderlich)."
        )

    rel_src = abs_src.relative_to(abs_home)
    dest = abs_stow / pkg / rel_src
    cur = abs_stow
    for part in (Path(pkg) / rel_src).parts:
        cur = cur / part
        try:
            st_cur = os.lstat(cur)
        except FileNotFoundError:
            break
        except OSError as e:
            fail(f"Prüfung des Zielpfads '{cur}' fehlgeschlagen: {os_err(e)}")

        if stat.S_ISLNK(st_cur.st_mode):
            fail(f"Zielpfad-Komponente '{cur}' im Stow-Verzeichnis ist ein Symlink.")
        if cur == dest:
            fail(f"Ziel '{dest}' existiert bereits.")
        if not stat.S_ISDIR(st_cur.st_mode):
            fail(
                f"Zielpfad-Komponente '{cur}' existiert bereits "
                f"und ist kein Verzeichnis."
            )

    try:
        os.chdir(abs_home)
    except OSError as e:
        fail(f"Wechsel nach '{abs_home}' fehlgeschlagen: {os_err(e)}")

    created_stow: Path | None = None
    try:
        created_stow = mkdir_secure_parents(abs_stow)
        if stow_raw.resolve(strict=True) != abs_stow:
            raise RuntimeError(
                f"Stow-Verzeichnis '{stow_raw}' wurde unerwartet umgeleitet"
            )
        st_stow_real = os.lstat(abs_stow)
        if not stat.S_ISDIR(st_stow_real.st_mode):
            raise RuntimeError(
                f"Stow-Verzeichnis '{abs_stow}' ist kein echtes Verzeichnis"
            )
        stow_mode = stat.S_IMODE(st_stow_real.st_mode)
        if stow_mode & 0o077:
            raise RuntimeError(
                f"Stow-Verzeichnis '{abs_stow}' erlaubt Zugriff für "
                f"Gruppe/Andere (Unix-Modus {stow_mode:04o})"
            )
    except (OSError, RuntimeError) as e:
        cleanup_created(abs_stow, created_stow)
        fail(
            f"Stow-Verzeichnis '{stow_raw}' konnte nicht sicher bereitgestellt "
            f"werden ({format_reason(e)}). Quelle '{abs_src}' ist unverändert."
        )

    created_dest = first_missing_ancestor(dest.parent)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        cleanup_created(dest.parent, created_dest)
        cleanup_created(abs_stow, created_stow)
        fail(
            f"Zielordner '{dest.parent}' konnte nicht angelegt werden ({os_err(e)}). "
            f"Quelle '{abs_src}' ist unverändert."
        )

    stow_started = False
    modes_touched = False
    try:
        move_path(abs_src, dest, is_dir, copy_checked=cross_device)
        stow_started = True

        res = subprocess.run(
            [
                "stow",
                "--no-folding",
                "-d",
                os.fspath(abs_stow),
                "-t",
                os.fspath(abs_home),
                f"--verbose={args.verbose}" if args.verbose else "",
                "-S",
                pkg
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="backslashreplace",
            check=False,
        )

        if res.returncode != 0:
            err_msg = res.stderr.strip() or res.stdout.strip()
            detail = f": {err_msg}" if err_msg else ""
            raise RuntimeError(f"stow beendet mit Code {res.returncode}{detail}")

        verify_stowed_tree(dest, abs_src, is_dir)

        if is_dir:
            modes_touched = True
            restore_dir_modes(abs_src, dir_modes)

        if args.verbose:
            if res.stdout:
                print(res.stdout, end="")
            if res.stderr:
                print(res.stderr, end="", file=sys.stderr)

    except (Exception, KeyboardInterrupt) as exc:
        reason = format_reason(exc)
        src_exists = path_present(abs_src)
        dest_exists = path_present(dest)

        if not stow_started:
            if not dest_exists and src_exists:
                cleanup_created(dest.parent, created_dest)
                cleanup_created(abs_stow, created_stow)
                fail(
                    f"Verschieben fehlgeschlagen ({reason}). "
                    f"Quelle '{abs_src}' ist unverändert."
                )
            if not (dest_exists and not src_exists):
                fail(
                    f"Verschieben unvollständig ({reason}). Kein automatisches "
                    f"Löschen zum Schutz vor Datenverlust. Bitte Quelle "
                    f"'{abs_src}' und Ziel '{dest}' manuell prüfen."
                )

        if not dest_exists:
            fail(
                f"{reason}. Ziel '{dest}' fehlt unerwartet. "
                f"Bitte '{abs_src}' und '{dest}' manuell prüfen."
            )

        perm_hint = (
            " Bitte dabei auch die Verzeichnisrechte prüfen."
            if modes_touched
            else ""
        )
        if not cleanup_partial_stow(abs_src, dest, is_dir):
            fail(
                f"{reason}. Rollback gestoppt, da '{abs_src}' unerwartete "
                f"Einträge enthält. Originaldaten liegen in '{dest}'.{perm_hint}"
            )
        try:
            move_path(dest, abs_src, is_dir, copy_checked=False)
        except (Exception, KeyboardInterrupt) as move_exc:
            move_detail = format_reason(move_exc)
            fail(
                f"{reason}. Rückverschieben fehlgeschlagen ({move_detail}). "
                f"Bitte '{dest}' und '{abs_src}' manuell prüfen.{perm_hint}"
            )
        cleanup_created(dest.parent, created_dest)
        cleanup_created(abs_stow, created_stow)
        fail(f"{reason}. Zurückgerollt.")


if __name__ == "__main__":
    main()
