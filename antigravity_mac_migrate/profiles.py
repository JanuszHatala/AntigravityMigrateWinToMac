"""Locate copied Antigravity IDE, Antigravity 2.0, Gemini, and CLI trees."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROFILE_NAMES = ("ide", "app", "gemini", "cli")

IDE_PRODUCT = "Antigravity IDE"
APP_PRODUCT = "Antigravity"


def support_dir(home: Path, product: str) -> Path:
    return home / "Library" / "Application Support" / product


@dataclass
class ResolvedProfile:
    name: str
    user_dirs: list[Path] = field(default_factory=list)
    dot_dirs: list[Path] = field(default_factory=list)
    content_dirs: list[Path] = field(default_factory=list)
    extra_files: list[Path] = field(default_factory=list)
    skill_dirs: list[Path] = field(default_factory=list)

    def present(self) -> bool:
        return any(
            path.exists()
            for path in (
                *self.content_dirs,
                *self.extra_files,
                *self.user_dirs,
                *self.dot_dirs,
            )
        )


@dataclass
class ProfileSelection:
    profiles: list[ResolvedProfile]
    warnings: list[str]


def resolve_profiles(home: Path, selected: list[str] | None = None) -> ProfileSelection:
    """Return every requested profile that has copied files.

    Missing trees are warnings. The Windows ``Antigravity`` folder is paired
    with the 2.0 app and is never attached to the IDE profile.
    """
    home = Path(home).expanduser()
    requested = _dedupe(selected) if selected else list(PROFILE_NAMES)
    unknown = [name for name in requested if name not in PROFILE_NAMES]
    if unknown:
        raise SystemExit(
            "Unknown profile "
            + ", ".join(unknown)
            + ". Use ide, app, gemini, or cli."
        )
    profiles: list[ResolvedProfile] = []
    warnings: list[str] = []
    for name in requested:
        profile, missing, notes = _build_profile(name, home)
        warnings.extend(missing)
        warnings.extend(notes)
        if profile.present():
            profiles.append(profile)
        elif selected:
            warnings.append(
                f"Profile {name} has no copied files. Nothing in that profile will be changed."
            )
    return ProfileSelection(profiles=profiles, warnings=warnings)


def _dedupe(names: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _build_profile(name: str, home: Path) -> tuple[ResolvedProfile, list[str], list[str]]:
    if name == "ide":
        return _build_ide(home)
    if name == "app":
        return _build_app(home)
    if name == "gemini":
        return _build_gemini(home)
    if name == "cli":
        return _build_cli(home)
    raise SystemExit(f"Unknown profile {name}")


def _missing(label: str, path: Path) -> str:
    return f"Missing {label}: {path}"


def _same_dir(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


def _build_ide(home: Path) -> tuple[ResolvedProfile, list[str], list[str]]:
    user = support_dir(home, IDE_PRODUCT) / "User"
    dot = home / ".antigravity-ide"
    gemini = home / ".gemini" / "antigravity-ide"
    argv = support_dir(home, IDE_PRODUCT) / "argv.json"
    missing: list[str] = []
    if not user.is_dir():
        missing.append(_missing("Antigravity IDE user data", user))
    if not dot.is_dir():
        missing.append(_missing("Antigravity IDE extensions", dot))
    if not gemini.is_dir():
        missing.append(_missing("Antigravity IDE Gemini data", gemini))
    profile = ResolvedProfile(name="ide")
    for path in (user, dot, gemini):
        if path.is_dir():
            profile.content_dirs.append(path)
    if user.is_dir():
        profile.user_dirs.append(user)
    if dot.is_dir():
        profile.dot_dirs.append(dot)
        if (dot / "skills").is_dir():
            profile.skill_dirs.append(dot / "skills")
    if gemini.is_dir() and (gemini / "skills").is_dir():
        profile.skill_dirs.append(gemini / "skills")
    if argv.is_file():
        profile.extra_files.append(argv)
    return profile, missing, []


def _build_app(home: Path) -> tuple[ResolvedProfile, list[str], list[str]]:
    user = support_dir(home, APP_PRODUCT) / "User"
    dot = home / ".antigravity"
    gemini = home / ".gemini" / "antigravity"
    argv = support_dir(home, APP_PRODUCT) / "argv.json"
    lower_root = support_dir(home, "antigravity")
    lower_user = lower_root / "User"
    canonical = support_dir(home, APP_PRODUCT)
    missing: list[str] = []
    notes: list[str] = []
    if not user.is_dir():
        missing.append(_missing("Antigravity 2.0 user data", user))
    if not dot.is_dir():
        missing.append(_missing("Antigravity 2.0 extensions", dot))
    if not gemini.is_dir():
        missing.append(_missing("Antigravity 2.0 Gemini data", gemini))
    profile = ResolvedProfile(name="app")
    for path in (user, dot, gemini):
        if path.is_dir():
            profile.content_dirs.append(path)
    if user.is_dir():
        profile.user_dirs.append(user)
    if lower_user.is_dir() and not _same_dir(lower_user, user):
        profile.user_dirs.append(lower_user)
        profile.content_dirs.append(lower_user)
        notes.append(
            "Using lowercase probe path for the Antigravity 2.0 app, not the IDE: "
            + str(lower_user)
        )
    elif lower_root.is_dir() and not _same_dir(lower_root, canonical):
        profile.content_dirs.append(lower_root)
        notes.append(
            "Using lowercase probe path for the Antigravity 2.0 app, not the IDE: "
            + str(lower_root)
        )
    if dot.is_dir():
        profile.dot_dirs.append(dot)
        if (dot / "skills").is_dir():
            profile.skill_dirs.append(dot / "skills")
    if gemini.is_dir() and (gemini / "skills").is_dir():
        profile.skill_dirs.append(gemini / "skills")
    if argv.is_file():
        profile.extra_files.append(argv)
    return profile, missing, notes


def _build_gemini(home: Path) -> tuple[ResolvedProfile, list[str], list[str]]:
    root = home / ".gemini"
    config = root / "config"
    rules = root / "GEMINI.md"
    missing: list[str] = []
    if not rules.is_file():
        missing.append(_missing("shared Gemini rules", rules))
    if not config.is_dir():
        missing.append(_missing("shared Gemini config", config))
    profile = ResolvedProfile(name="gemini")
    if config.is_dir():
        profile.content_dirs.append(config)
        if (config / "skills").is_dir():
            profile.skill_dirs.append(config / "skills")
    if rules.is_file():
        profile.extra_files.append(rules)
    return profile, missing, []


def _build_cli(home: Path) -> tuple[ResolvedProfile, list[str], list[str]]:
    cli = home / ".gemini" / "antigravity-cli"
    if not cli.is_dir():
        return (
            ResolvedProfile(name="cli"),
            [_missing("Antigravity CLI data", cli)],
            [],
        )
    return (
        ResolvedProfile(name="cli", content_dirs=[cli], skill_dirs=[cli]),
        [],
        [],
    )
