"""Shared types and Windows primitives for ownership-safe uninstall."""

from __future__ import annotations

import ctypes
import os
import secrets
import shutil
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UninstallReport:
    """Deterministic paths removed, preserved, or already missing."""

    removed: list[str]
    preserved: list[str]
    missing: list[str]


_FILE_ATTRIBUTE_DIRECTORY = 0x10
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_READ_ATTRIBUTES = 0x80
_FILE_SHARE_READ = 0x1
_OPEN_EXISTING = 3


def _is_link_or_reparse_point(path: Path) -> bool:
    """Return whether ``path`` redirects traversal through a link-like object."""
    path_stat = path.lstat()
    return stat.S_ISLNK(path_stat.st_mode) or bool(
        getattr(path_stat, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", _FILE_ATTRIBUTE_REPARSE_POINT)
    )


@contextmanager
def _locked_windows_parent_directories(root: Path, target: Path) -> Iterator[None]:
    """Pin every ancestor through the target parent against replacement."""
    if os.name != "nt":
        raise OSError("Windows pathname uninstall requested on a non-Windows platform")

    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"unsafe uninstall target outside {root}: {target}") from exc

    handles: list[int] = []
    try:
        current = root
        for component in relative.parts[:-1]:
            handles.append(_open_locked_windows_directory(current))
            current /= component
        handles.append(_open_locked_windows_directory(current))
        yield
    finally:
        for handle in reversed(handles):
            _close_windows_handle(handle)


def _open_locked_windows_directory(path: Path) -> int:
    """Open one real directory without granting write or delete sharing."""
    from ctypes import wintypes

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        error = ctypes.get_last_error()
        raise OSError(error, f"cannot lock Windows uninstall boundary {path}", path)

    information = _ByHandleFileInformation()
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    if not get_information(handle, ctypes.byref(information)):
        error = ctypes.get_last_error()
        _close_windows_handle(handle)
        raise OSError(error, f"cannot inspect Windows uninstall boundary {path}", path)
    if not information.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY:
        _close_windows_handle(handle)
        raise ValueError(f"uninstall boundary is not a directory: {path}")
    if information.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        _close_windows_handle(handle)
        raise ValueError(f"refusing to cross Windows reparse-point boundary: {path}")
    return int(handle)


def _close_windows_handle(handle: int) -> None:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    close_handle(handle)


def _remove_path_on_windows(
    root: Path, target: Path, revalidate: Callable[[Path], None]
) -> None:
    """Quarantine, validate, and remove one leaf while its parents are pinned."""
    with _locked_windows_parent_directories(root, target):
        quarantine = target.with_name(
            f".{target.name}.{os.getpid()}.{secrets.token_hex(12)}.maid-uninstall"
        )
        os.replace(target, quarantine)
        try:
            revalidate(quarantine)
            quarantine_stat = quarantine.lstat()
            if _is_link_or_reparse_point(quarantine):
                if (
                    getattr(quarantine_stat, "st_file_attributes", 0)
                    & _FILE_ATTRIBUTE_DIRECTORY
                ):
                    os.rmdir(quarantine)
                else:
                    os.unlink(quarantine)
            elif stat.S_ISDIR(quarantine_stat.st_mode):
                shutil.rmtree(quarantine)
            else:
                os.unlink(quarantine)
        except BaseException as exc:
            _restore_windows_quarantine(target, quarantine, exc)
            raise


def _replace_file_on_windows(
    root: Path,
    target: Path,
    content: bytes,
    mode: int,
    revalidate: Callable[[Path], None],
) -> None:
    """Quarantine, validate, and atomically replace a file with rollback."""
    temporary = target.with_name(
        f".{target.name}.{os.getpid()}.{secrets.token_hex(12)}.maid-uninstall.tmp"
    )
    with _locked_windows_parent_directories(root, target):
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(descriptor)
            temporary_stat = temporary.lstat()
            temporary_identity = (
                temporary_stat.st_dev,
                temporary_stat.st_ino,
                temporary_stat.st_mode,
                temporary_stat.st_size,
            )
            quarantine = target.with_name(
                f".{target.name}.{os.getpid()}.{secrets.token_hex(12)}.maid-uninstall"
            )
            os.replace(target, quarantine)
            try:
                revalidate(quarantine)
            except BaseException as exc:
                _restore_windows_quarantine(target, quarantine, exc)
                raise
            try:
                os.replace(temporary, target)
            except BaseException as exc:
                _restore_windows_quarantine(target, quarantine, exc)
                raise
            try:
                os.unlink(quarantine)
            except BaseException as exc:
                _rollback_windows_replacement(
                    target,
                    quarantine,
                    content,
                    temporary_identity,
                    exc,
                )
                raise
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _restore_windows_quarantine(
    target: Path, quarantine: Path, original_error: BaseException
) -> None:
    """Restore a quarantined leaf, or fail loudly without overwriting new data."""
    if not os.path.lexists(quarantine):
        return
    try:
        os.rename(quarantine, target)
    except FileExistsError as rollback_error:
        raise OSError(
            "Windows uninstall rollback found a new target; preserved quarantine "
            f"at {quarantine}"
        ) from rollback_error
    except OSError as rollback_error:
        raise OSError(
            f"Windows uninstall rollback failed; preserved quarantine at {quarantine}"
        ) from rollback_error


def _rollback_windows_replacement(
    target: Path,
    original_quarantine: Path,
    expected_content: bytes,
    expected_identity: tuple[int, int, int, int],
    original_error: BaseException,
) -> None:
    """Quarantine and validate an installed replacement before rollback."""
    replacement_quarantine = target.with_name(
        f".{target.name}.{os.getpid()}.{secrets.token_hex(12)}.maid-uninstall"
    )
    try:
        os.replace(target, replacement_quarantine)
    except OSError as quarantine_error:
        raise OSError(
            "Windows uninstall could not quarantine a replacement for rollback; "
            f"preserved original quarantine at {original_quarantine}"
        ) from quarantine_error

    try:
        replacement_stat = replacement_quarantine.lstat()
        replacement_identity = (
            replacement_stat.st_dev,
            replacement_stat.st_ino,
            replacement_stat.st_mode,
            replacement_stat.st_size,
        )
        replacement_matches = (
            replacement_identity == expected_identity
            and replacement_quarantine.read_bytes() == expected_content
        )
    except OSError as validation_error:
        _restore_original_with_replacement_context(
            target,
            original_quarantine,
            replacement_quarantine,
            validation_error,
        )
        raise OSError(
            "Windows uninstall could not inspect its quarantined replacement; "
            f"retained replacement state at {replacement_quarantine}"
        ) from validation_error
    if not replacement_matches:
        _restore_original_with_replacement_context(
            target,
            original_quarantine,
            replacement_quarantine,
            original_error,
        )
        raise OSError(
            "Windows uninstall replacement changed before rollback; preserved "
            f"replacement quarantine at {replacement_quarantine}"
        ) from original_error

    try:
        os.unlink(replacement_quarantine)
    except OSError as cleanup_error:
        _restore_original_with_replacement_context(
            target,
            original_quarantine,
            replacement_quarantine,
            cleanup_error,
        )
        raise OSError(
            "Windows uninstall could not remove its replacement during rollback; "
            f"preserved replacement quarantine at {replacement_quarantine}"
        ) from cleanup_error
    _restore_windows_quarantine(target, original_quarantine, original_error)


def _restore_original_with_replacement_context(
    target: Path,
    original_quarantine: Path,
    replacement_quarantine: Path,
    original_error: BaseException,
) -> None:
    """Restore the original or report both quarantines on nested failure."""
    try:
        _restore_windows_quarantine(target, original_quarantine, original_error)
    except OSError as restore_error:
        raise OSError(
            "Windows uninstall rollback retained both original quarantine "
            f"{original_quarantine} and replacement quarantine "
            f"{replacement_quarantine}"
        ) from restore_error
