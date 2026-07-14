from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .research_engine import sha256_hex


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLUEPRINT_KNOWLEDGE_ROOT = REPO_ROOT
DEFAULT_BLUEPRINT_MANIFEST_PATH = REPO_ROOT / "knowledge" / "blueprint" / "manifest.json"


_SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _safe_identifier(value: str, field_name: str) -> str:
    safe = str(value or "").strip()
    if not safe or safe in {".", ".."} or Path(safe).name != safe or "/" in safe or "\\" in safe:
        raise ValueError(f"{field_name} must be a safe identifier")
    return safe


def _safe_version(value: str, field_name: str) -> str:
    version = str(value or "").strip()
    if not version or not _SAFE_VERSION_RE.fullmatch(version):
        raise ValueError(f"{field_name} must be a safe semantic version")
    return version


def _ensure_tuple_strings(items: Any, field_name: str) -> tuple[str, ...]:
    if items is None:
        return ()
    if not isinstance(items, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of strings")
    values = []
    for item in items:
        value = str(item).strip()
        if not value:
            raise ValueError(f"{field_name} must not contain empty values")
        values.append(value)
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class BlueprintKnowledgeAsset:
    asset_id: str
    version: str
    repository_path: str
    drive_document_id: str
    drive_url: str
    source_title: str
    owner: str
    status: str
    source_modified_at: str
    checksum: str
    dependencies: tuple[str, ...] = ()
    compatibility_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _safe_identifier(self.asset_id, "asset_id")
        _safe_version(self.version, "version")
        repository_path = str(self.repository_path).strip()
        if not repository_path:
            raise ValueError("repository_path must not be empty")
        if Path(repository_path).is_absolute():
            raise ValueError("repository_path must be repository relative")
        object.__setattr__(self, "repository_path", repository_path)
        object.__setattr__(self, "drive_document_id", str(self.drive_document_id).strip())
        object.__setattr__(self, "drive_url", str(self.drive_url).strip())
        object.__setattr__(self, "source_title", str(self.source_title).strip())
        object.__setattr__(self, "owner", str(self.owner).strip())
        object.__setattr__(self, "status", str(self.status).strip().lower())
        object.__setattr__(self, "source_modified_at", str(self.source_modified_at).strip())
        object.__setattr__(self, "checksum", str(self.checksum).strip())
        object.__setattr__(self, "dependencies", _ensure_tuple_strings(self.dependencies, "dependencies"))
        object.__setattr__(
            self,
            "compatibility_notes",
            _ensure_tuple_strings(self.compatibility_notes, "compatibility_notes"),
        )

    def path(self, root: str | Path = REPO_ROOT) -> Path:
        return (Path(root).resolve() / self.repository_path).resolve()

    def read_text(self, root: str | Path = REPO_ROOT) -> str:
        return self.path(root).read_text(encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "version": self.version,
            "repository_path": self.repository_path,
            "drive_document_id": self.drive_document_id,
            "drive_url": self.drive_url,
            "source_title": self.source_title,
            "owner": self.owner,
            "status": self.status,
            "source_modified_at": self.source_modified_at,
            "checksum": self.checksum,
            "dependencies": list(self.dependencies),
            "compatibility_notes": list(self.compatibility_notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlueprintKnowledgeAsset":
        return cls(
            asset_id=str(data.get("asset_id", "")).strip(),
            version=str(data.get("version", "")).strip(),
            repository_path=str(data.get("repository_path", "")).strip(),
            drive_document_id=str(data.get("drive_document_id", "")).strip(),
            drive_url=str(data.get("drive_url", "")).strip(),
            source_title=str(data.get("source_title", "")).strip(),
            owner=str(data.get("owner", "")).strip() or "Narratiive",
            status=str(data.get("status", "")).strip() or "approved",
            source_modified_at=str(data.get("source_modified_at", "")).strip(),
            checksum=str(data.get("checksum", "")).strip(),
            dependencies=tuple(data.get("dependencies") or ()),
            compatibility_notes=tuple(data.get("compatibility_notes") or ()),
        )


@dataclass(frozen=True, slots=True)
class BlueprintCanonBundleComponent:
    asset_id: str
    version: str
    checksum: str
    repository_path: str

    def __post_init__(self) -> None:
        _safe_identifier(self.asset_id, "asset_id")
        _safe_version(self.version, "version")
        repository_path = str(self.repository_path).strip()
        if not repository_path:
            raise ValueError("repository_path must not be empty")
        object.__setattr__(self, "repository_path", repository_path)
        object.__setattr__(self, "checksum", str(self.checksum).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "version": self.version,
            "checksum": self.checksum,
            "repository_path": self.repository_path,
        }


@dataclass(frozen=True, slots=True)
class BlueprintCanonBundle:
    bundle_id: str
    version: str
    status: str
    prompt_asset_id: str
    supporting_asset_ids: tuple[str, ...]
    components: tuple[BlueprintCanonBundleComponent, ...]
    checksum: str
    compatibility_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _safe_identifier(self.bundle_id, "bundle_id")
        _safe_version(self.version, "version")
        object.__setattr__(self, "status", str(self.status).strip().lower())
        _safe_identifier(self.prompt_asset_id, "prompt_asset_id")
        object.__setattr__(
            self,
            "supporting_asset_ids",
            _ensure_tuple_strings(self.supporting_asset_ids, "supporting_asset_ids"),
        )
        object.__setattr__(self, "checksum", str(self.checksum).strip())
        object.__setattr__(
            self,
            "components",
            tuple(self.components),
        )
        object.__setattr__(
            self,
            "compatibility_notes",
            _ensure_tuple_strings(self.compatibility_notes, "compatibility_notes"),
        )

    @property
    def canon_version(self) -> str:
        return self.version

    def component(self, asset_id: str) -> BlueprintCanonBundleComponent:
        asset_id = _safe_identifier(asset_id, "asset_id")
        for component in self.components:
            if component.asset_id == asset_id:
                return component
        raise KeyError(f"bundle component not found: {asset_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "version": self.version,
            "canon_version": self.canon_version,
            "status": self.status,
            "prompt_asset_id": self.prompt_asset_id,
            "supporting_asset_ids": list(self.supporting_asset_ids),
            "components": [component.to_dict() for component in self.components],
            "checksum": self.checksum,
            "compatibility_notes": list(self.compatibility_notes),
        }


BlueprintCanonVersion = BlueprintCanonBundle


@dataclass(frozen=True, slots=True)
class BlueprintSchemaSlide:
    slide_no: int
    slide_name: str
    act: str
    purpose: str
    visual_type: str
    layout_type: str
    content_requirements: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    so_what_test: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slide_no": self.slide_no,
            "slide_name": self.slide_name,
            "act": self.act,
            "purpose": self.purpose,
            "visual_type": self.visual_type,
            "layout_type": self.layout_type,
            "content_requirements": list(self.content_requirements),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "so_what_test": self.so_what_test,
        }


@dataclass(frozen=True, slots=True)
class BlueprintSchemaV3:
    source_path: str
    acts: tuple[str, ...]
    slides: tuple[BlueprintSchemaSlide, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "acts": list(self.acts),
            "slides": [slide.to_dict() for slide in self.slides],
        }


class BlueprintKnowledgeRegistry:
    """Read-only registry for the canonical Blueprint assets and bundle."""

    def __init__(
        self,
        root: str | Path = DEFAULT_BLUEPRINT_KNOWLEDGE_ROOT,
        *,
        manifest_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.manifest_path = Path(manifest_path or (self.root / "manifest.json")).resolve()
        if not self.manifest_path.is_file():
            raise FileNotFoundError(f"Blueprint manifest not found: {self.manifest_path}")
        self._manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self._assets_by_key: dict[tuple[str, str], BlueprintKnowledgeAsset] = {}
        self._assets_by_id: dict[str, BlueprintKnowledgeAsset] = {}
        self._bundles_by_key: dict[tuple[str, str], BlueprintCanonBundle] = {}
        self._active_bundle_key: tuple[str, str] | None = None
        self._load()

    @classmethod
    def from_default(cls) -> "BlueprintKnowledgeRegistry":
        return cls(DEFAULT_BLUEPRINT_KNOWLEDGE_ROOT, manifest_path=DEFAULT_BLUEPRINT_MANIFEST_PATH)

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(_stable_json(self._manifest))

    def asset(self, asset_id: str, version: str | None = None) -> BlueprintKnowledgeAsset:
        asset_id = _safe_identifier(asset_id, "asset_id")
        if version is None:
            matches = [asset for (key_asset_id, _), asset in self._assets_by_key.items() if key_asset_id == asset_id]
            if not matches:
                raise KeyError(f"unknown Blueprint asset: {asset_id}")
            if len(matches) > 1:
                raise ValueError(f"ambiguous Blueprint asset version for: {asset_id}")
            return matches[0]
        key = (asset_id, _safe_version(version, "version"))
        try:
            return self._assets_by_key[key]
        except KeyError as exc:
            raise KeyError(f"unknown Blueprint asset: {asset_id}@{version}") from exc

    def bundle(self, bundle_id: str | None = None, version: str | None = None) -> BlueprintCanonBundle:
        if bundle_id is None:
            return self.active_bundle()
        bundle_id = _safe_identifier(bundle_id, "bundle_id")
        if version is None:
            matches = [bundle for (key_bundle_id, _), bundle in self._bundles_by_key.items() if key_bundle_id == bundle_id]
            if not matches:
                raise KeyError(f"unknown Blueprint bundle: {bundle_id}")
            if len(matches) > 1:
                raise ValueError(f"ambiguous Blueprint bundle version for: {bundle_id}")
            return matches[0]
        key = (bundle_id, _safe_version(version, "version"))
        try:
            return self._bundles_by_key[key]
        except KeyError as exc:
            raise KeyError(f"unknown Blueprint bundle: {bundle_id}@{version}") from exc

    def active_bundle(self) -> BlueprintCanonBundle:
        if self._active_bundle_key is None:
            raise KeyError("no active Blueprint bundle configured")
        return self._bundles_by_key[self._active_bundle_key]

    def schema(self) -> BlueprintSchemaV3:
        asset = self.asset("blueprint_schema_v3")
        return _load_schema(asset.read_text(self.root), asset.repository_path)

    def prompt_asset(self, bundle: BlueprintCanonBundle | None = None) -> BlueprintKnowledgeAsset:
        bundle = bundle or self.active_bundle()
        return self.asset(bundle.prompt_asset_id)

    def supporting_assets(self, bundle: BlueprintCanonBundle | None = None) -> tuple[BlueprintKnowledgeAsset, ...]:
        bundle = bundle or self.active_bundle()
        return tuple(self.asset(asset_id) for asset_id in bundle.supporting_asset_ids)

    def bundle_asset_contents(self, bundle: BlueprintCanonBundle | None = None) -> dict[str, str]:
        bundle = bundle or self.active_bundle()
        contents: dict[str, str] = {}
        for component in bundle.components:
            asset = self.asset(component.asset_id, component.version)
            contents[asset.asset_id] = asset.read_text(self.root)
        return contents

    def prompt_metadata(self, bundle: BlueprintCanonBundle | None = None) -> dict[str, Any]:
        bundle = bundle or self.active_bundle()
        prompt_asset = self.prompt_asset(bundle)
        supporting_assets = self.supporting_assets(bundle)
        return {
            "knowledge_root": str(self.root),
            "manifest_path": str(self.manifest_path),
            "bundle": bundle.to_dict(),
            "prompt_asset": prompt_asset.to_dict(),
            "supporting_instruction_sources": [asset.to_dict() for asset in supporting_assets],
            "source_checksum": prompt_asset.checksum,
            "source_path": str(prompt_asset.path(self.root)),
        }

    def _load(self) -> None:
        manifest_assets = self._manifest.get("assets")
        manifest_bundles = self._manifest.get("bundles")
        if not isinstance(manifest_assets, list) or not manifest_assets:
            raise ValueError("manifest must contain an assets list")
        if not isinstance(manifest_bundles, list) or not manifest_bundles:
            raise ValueError("manifest must contain a bundles list")

        for raw_asset in manifest_assets:
            if not isinstance(raw_asset, Mapping):
                raise ValueError("asset entries must be objects")
            asset = BlueprintKnowledgeAsset.from_dict(dict(raw_asset))
            key = (asset.asset_id, asset.version)
            if key in self._assets_by_key:
                raise ValueError(f"duplicate Blueprint asset identifier: {asset.asset_id}@{asset.version}")
            if asset.asset_id in self._assets_by_id:
                raise ValueError(f"duplicate Blueprint asset identifier: {asset.asset_id}")
            path = asset.path(self.root)
            if not path.is_file():
                raise FileNotFoundError(f"Blueprint asset file not found: {path}")
            content = path.read_text(encoding="utf-8")
            if sha256_hex(content) != asset.checksum:
                raise ValueError(f"Blueprint asset checksum mismatch: {asset.asset_id}")
            self._assets_by_key[key] = asset
            self._assets_by_id[asset.asset_id] = asset

        for raw_bundle in manifest_bundles:
            if not isinstance(raw_bundle, Mapping):
                raise ValueError("bundle entries must be objects")
            bundle = self._load_bundle(dict(raw_bundle))
            key = (bundle.bundle_id, bundle.version)
            if key in self._bundles_by_key:
                raise ValueError(f"duplicate Blueprint bundle identifier: {bundle.bundle_id}@{bundle.version}")
            self._bundles_by_key[key] = bundle
            if bundle.status == "active":
                if self._active_bundle_key is not None:
                    raise ValueError("multiple active Blueprint bundles configured")
                self._active_bundle_key = key

        if self._active_bundle_key is None:
            raise ValueError("manifest must define one active Blueprint bundle")

    def _load_bundle(self, raw_bundle: Mapping[str, Any]) -> BlueprintCanonBundle:
        components_data = raw_bundle.get("components")
        if not isinstance(components_data, list) or not components_data:
            raise ValueError("bundle components must be a non-empty list")
        components: list[BlueprintCanonBundleComponent] = []
        seen_assets: set[str] = set()
        for raw_component in components_data:
            if not isinstance(raw_component, Mapping):
                raise ValueError("bundle component entries must be objects")
            component = BlueprintCanonBundleComponent(
                asset_id=str(raw_component.get("asset_id", "")).strip(),
                version=str(raw_component.get("version", "")).strip(),
                checksum=str(raw_component.get("checksum", "")).strip(),
                repository_path=str(raw_component.get("repository_path", "")).strip(),
            )
            if component.asset_id in seen_assets:
                raise ValueError(f"duplicate bundle component: {component.asset_id}")
            seen_assets.add(component.asset_id)
            asset = self.asset(component.asset_id, component.version)
            if asset.checksum != component.checksum:
                raise ValueError(
                    f"bundle component checksum mismatch: {component.asset_id}@{component.version}"
                )
            components.append(component)

        bundle = BlueprintCanonBundle(
            bundle_id=str(raw_bundle.get("bundle_id", "")).strip(),
            version=str(raw_bundle.get("version", "")).strip(),
            status=str(raw_bundle.get("status", "")).strip() or "active",
            prompt_asset_id=str(raw_bundle.get("prompt_asset_id", "")).strip(),
            supporting_asset_ids=tuple(raw_bundle.get("supporting_asset_ids") or ()),
            components=tuple(components),
            checksum=str(raw_bundle.get("checksum", "")).strip(),
            compatibility_notes=tuple(raw_bundle.get("compatibility_notes") or ()),
        )
        expected_checksum = sha256_hex(
            _stable_json(
                {
                    "bundle_id": bundle.bundle_id,
                    "version": bundle.version,
                    "canon_version": bundle.canon_version,
                    "status": bundle.status,
                    "prompt_asset_id": bundle.prompt_asset_id,
                    "supporting_asset_ids": list(bundle.supporting_asset_ids),
                    "components": [component.to_dict() for component in bundle.components],
                    "compatibility_notes": list(bundle.compatibility_notes),
                }
            )
        )
        if bundle.checksum and bundle.checksum != expected_checksum:
            raise ValueError(f"Blueprint bundle checksum mismatch: {bundle.bundle_id}@{bundle.version}")
        if not bundle.checksum:
            object.__setattr__(bundle, "checksum", expected_checksum)

        if bundle.prompt_asset_id not in {component.asset_id for component in bundle.components}:
            raise ValueError(f"bundle prompt asset is missing: {bundle.prompt_asset_id}")
        for supporting_asset_id in bundle.supporting_asset_ids:
            if supporting_asset_id not in {component.asset_id for component in bundle.components}:
                raise ValueError(f"bundle supporting asset is missing: {supporting_asset_id}")
        return bundle


def _load_schema(text: str, repository_path: str) -> BlueprintSchemaV3:
    act_re = re.compile(r"^##\s+Act\s+\d+\s+—\s+(.+)\s*$")
    slide_re = re.compile(r"^###\s+Slide\s+(\d+)\s+—\s+(.+)\s*$")
    field_re = re.compile(r"^\s*-\s*([^:]+):\s*(.*\S)\s*$")
    acts: list[str] = []
    slides: list[BlueprintSchemaSlide] = []
    current_act = ""
    current_slide: dict[str, Any] | None = None

    def finish_slide() -> None:
        nonlocal current_slide
        if not current_slide:
            return
        slides.append(
            BlueprintSchemaSlide(
                slide_no=int(current_slide["slide_no"]),
                slide_name=str(current_slide.get("slide_name", "")).strip(),
                act=current_slide.get("act", current_act),
                purpose=str(current_slide.get("purpose", "")).strip(),
                visual_type=str(current_slide.get("visual_type", "")).strip(),
                layout_type=str(current_slide.get("layout_type", "")).strip(),
                content_requirements=tuple(current_slide.get("content_requirements", ())),
                inputs=tuple(current_slide.get("inputs", ())),
                outputs=tuple(current_slide.get("outputs", ())),
                so_what_test=str(current_slide.get("so_what_test", "")).strip(),
            )
        )
        current_slide = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        act_match = act_re.match(line)
        if act_match:
            finish_slide()
            current_act = act_match.group(1).strip()
            acts.append(current_act)
            continue
        slide_match = slide_re.match(line)
        if slide_match:
            finish_slide()
            current_slide = {
                "slide_no": int(slide_match.group(1)),
                "slide_name": slide_match.group(2).strip(),
                "act": current_act,
                "content_requirements": [],
                "inputs": [],
                "outputs": [],
            }
            continue
        if current_slide is None:
            continue
        field_match = field_re.match(line)
        if field_match:
            key = field_match.group(1).strip().lower().replace(" ", "_")
            value = field_match.group(2).strip()
            if key in {"purpose", "visual_type", "layout_type", "so_what_test"}:
                current_slide[key] = value
            elif key in {"content_requirements", "inputs", "outputs"}:
                current_slide.setdefault(key, []).append(value)
            continue
    finish_slide()
    if len(acts) != 6:
        raise ValueError(f"Blueprint schema must define 6 acts, found {len(acts)}")
    if len(slides) != 30:
        raise ValueError(f"Blueprint schema must define 30 slides, found {len(slides)}")
    return BlueprintSchemaV3(
        source_path=repository_path,
        acts=tuple(dict.fromkeys(acts)),
        slides=tuple(sorted(slides, key=lambda item: item.slide_no)),
    )
