"""Парсер Lithium ECAD проектов (.lpr/.lsc/.lbo).

Lithium-проект — три XML-файла:
  .lpr — project: библиотека packages/components, layers, net classes
  .lsc — schematic: ERC config, cache, pages с part-placement, fragments (nets), ports
  .lbo — pcb layout: layers, fragments, pads, vias, traces

Корневой файл имеет нестандартную структуру (два root-элемента подряд):

    <?xml version="1.0" encoding="utf-8"?>
    <lithium_ecad version="2.0.0"/>
    <schematic format="2">...</schematic>

Поэтому перед парсингом оборачиваем содержимое в синтетический `<root>`.

Парсер не реконструирует геометрию символов (cid → component name связь
не явная в файлах), но извлекает всё для structured-summary импорта:
ERC, cache, pages, fragments (nets), ports, layers, net classes.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

XML_DECL_RE = re.compile(r"^\s*<\?xml[^?]*\?>\s*", re.MULTILINE)
LITHIUM_HEADER_RE = re.compile(r"<lithium_ecad[^/]*/>")
ATTR_VALUE_RE = re.compile(r'="([^"]*)"')


def _escape_attr_brackets(text: str) -> str:
    """Lithium хранит placeholder-теги внутри атрибутов: `name="<agree>"`.
    Это невалидный XML — экранируем `<` и `>` внутри значений атрибутов.
    """
    def repl(match: re.Match[str]) -> str:
        val = match.group(1)
        if "<" not in val and ">" not in val:
            return match.group(0)
        val = val.replace("<", "&lt;").replace(">", "&gt;")
        return f'="{val}"'
    return ATTR_VALUE_RE.sub(repl, text)


class LithiumImportError(Exception):
    """Содержательная ошибка парсинга — пробрасывается в view."""


@dataclass
class LithiumProject:
    """Структурированный импорт Lithium-проекта."""
    version: str = ""
    project_format: str = ""
    schematic_format: str = ""
    pcb_format: str = ""

    packages: list[dict[str, str]] = field(default_factory=list)
    components: list[dict[str, str]] = field(default_factory=list)
    layers: list[dict[str, str]] = field(default_factory=list)
    net_classes: list[dict[str, str]] = field(default_factory=list)

    erc_rules: dict[str, int] = field(default_factory=dict)
    cache: list[dict[str, str]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    nets: list[dict[str, Any]] = field(default_factory=list)
    ports: list[dict[str, Any]] = field(default_factory=list)

    pcb_layers: list[dict[str, str]] = field(default_factory=list)
    pcb_traces_count: int = 0
    pcb_vias_count: int = 0
    pcb_pads_count: int = 0

    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project_format": self.project_format,
            "schematic_format": self.schematic_format,
            "pcb_format": self.pcb_format,
            "packages_count": len(self.packages),
            "components": self.components,
            "components_count": len(self.components),
            "layers": self.layers,
            "net_classes": self.net_classes,
            "erc_rules": self.erc_rules,
            "erc_rules_count": len(self.erc_rules),
            "cache": self.cache,
            "pages": [
                {
                    "name": p.get("name"),
                    "w": p.get("w"),
                    "h": p.get("h"),
                    "parts_count": len(p.get("parts", [])),
                }
                for p in self.pages
            ],
            "parts_count": sum(len(p.get("parts", [])) for p in self.pages),
            "nets_count": len(self.nets),
            "nets_named": [n["name"] for n in self.nets if n.get("name")][:50],
            "ports": self.ports,
            "ports_count": len(self.ports),
            "pcb_layers": self.pcb_layers,
            "pcb_traces_count": self.pcb_traces_count,
            "pcb_vias_count": self.pcb_vias_count,
            "pcb_pads_count": self.pcb_pads_count,
            "warnings": self.warnings,
        }


def _wrap_lithium_xml(text: str) -> ET.Element:
    """Lithium-файл = два root-элемента. Оборачиваем в синтетический <root>."""
    if not text or not text.strip():
        raise LithiumImportError("Пустой файл")
    stripped = XML_DECL_RE.sub("", text, count=1)
    stripped = _escape_attr_brackets(stripped)
    wrapped = f"<root>{stripped}</root>"
    try:
        return ET.fromstring(wrapped)
    except ET.ParseError as exc:
        raise LithiumImportError(f"Невалидный XML: {exc}") from exc


def _read_lithium_version(root: ET.Element) -> str:
    header = root.find("lithium_ecad")
    return header.get("version", "") if header is not None else ""


def parse_lpr(text: str) -> dict[str, Any]:
    """Распарсить .lpr (project): packages, components, layers, net classes."""
    root = _wrap_lithium_xml(text)
    version = _read_lithium_version(root)
    project = root.find("project")
    if project is None:
        raise LithiumImportError("В .lpr не найден <project>")

    project_format = project.get("format", "")
    # В Lithium .lpr реальная иерархия — <project><library><content>...</content>
    # <layers>...</layers></library><classes>...</classes></project>.
    # Тестовый минимальный .lpr использует упрощённый layout без <library> —
    # поддерживаем оба варианта.
    content = project.find("library/content") or project.find("content")
    packages: list[dict[str, str]] = []
    components: list[dict[str, str]] = []
    if content is not None:
        for pkg in content.findall("packages/package"):
            packages.append({
                "name": pkg.get("name", ""),
                "status": pkg.get("status", ""),
                "description": (pkg.text or "").strip(),
            })
        for comp in content.findall("components/component"):
            part = comp.find("part")
            pkg = comp.find("package")
            components.append({
                "name": comp.get("name", ""),
                "refdes": comp.get("refdes", ""),
                "value": comp.get("value", ""),
                "part": part.get("name", "") if part is not None else "",
                "package": pkg.get("name", "") if pkg is not None else "",
            })

    layers = [
        {"id": layer.get("id", ""), "name": layer.get("name", "")}
        for layer in (
            project.findall("library/layers/layer")
            or project.findall("layers/layer")
        )
    ]

    net_classes = []
    for cls in project.findall("classes/class"):
        net_classes.append({
            "name": cls.get("name", ""),
            "width_default": cls.get("width_default", ""),
            "width_min": cls.get("width_min", ""),
            "clearance_min": cls.get("clearance_min", ""),
            "drill_min": cls.get("drill_min", ""),
        })

    return {
        "version": version,
        "project_format": project_format,
        "packages": packages,
        "components": components,
        "layers": layers,
        "net_classes": net_classes,
    }


def parse_lsc(text: str) -> dict[str, Any]:
    """Распарсить .lsc (schematic): ERC, cache, pages, fragments (nets), ports."""
    root = _wrap_lithium_xml(text)
    version = _read_lithium_version(root)
    schematic = root.find("schematic")
    if schematic is None:
        raise LithiumImportError("В .lsc не найден <schematic>")

    schematic_format = schematic.get("format", "")

    erc_rules: dict[str, int] = {}
    for rule in schematic.findall("erc/rule"):
        try:
            erc_rules[rule.get("param", "")] = int(rule.get("value", "0"))
        except ValueError:
            continue

    cache: list[dict[str, str]] = []
    for cmp in schematic.findall("cache/cmp"):
        cache.append({
            "name": cmp.get("name", ""),
            "pkg": cmp.get("pkg", ""),
        })

    pages: list[dict[str, Any]] = []
    nets: list[dict[str, Any]] = []
    ports: list[dict[str, Any]] = []

    pages_el = schematic.find("pages")
    if pages_el is not None:
        for page in pages_el.findall("page"):
            parts = []
            for part in page.findall("parts/part"):
                parts.append({
                    "cid": part.get("cid", ""),
                    "x": part.get("x", ""),
                    "y": part.get("y", ""),
                    "rot": part.get("rot", "0"),
                    "mirror": part.get("mirror", ""),
                })
            pages.append({
                "name": page.get("name", ""),
                "w": page.get("w", ""),
                "h": page.get("h", ""),
                "parts": parts,
            })

            for port in page.findall("ports/port"):
                ports.append({
                    "sym": port.get("sym", ""),
                    "name": port.get("name", ""),
                    "x": port.get("x", ""),
                    "y": port.get("y", ""),
                    "rot": port.get("rot", "0"),
                })

            for fragment in page.findall("fragments/fragment"):
                rpins = [
                    {"id": rp.get("id", ""), "name": rp.get("name", "")}
                    for rp in fragment.findall("rpin")
                ]
                wires_count = len(fragment.findall("wire"))
                junctions_count = len(fragment.findall("junction"))
                labels = [
                    {"x": lbl.get("x", ""), "y": lbl.get("y", "")}
                    for lbl in fragment.findall("label")
                ]
                nets.append({
                    "name": fragment.get("net", ""),
                    "page": page.get("name", ""),
                    "rpins": rpins,
                    "rpins_count": len(rpins),
                    "wires_count": wires_count,
                    "junctions_count": junctions_count,
                    "labels": labels,
                })

    return {
        "version": version,
        "schematic_format": schematic_format,
        "erc_rules": erc_rules,
        "cache": cache,
        "pages": pages,
        "nets": nets,
        "ports": ports,
    }


def parse_lbo(text: str) -> dict[str, Any]:
    """Распарсить .lbo (PCB): layers, traces/vias/pads counts."""
    root = _wrap_lithium_xml(text)
    version = _read_lithium_version(root)
    pcb = root.find("pcb")
    if pcb is None:
        raise LithiumImportError("В .lbo не найден <pcb>")

    pcb_format = pcb.get("format", "")
    layers = [
        {"id": layer.get("id", ""), "name": layer.get("name", "")}
        for layer in pcb.findall("layers/layer")
    ]

    traces_count = len(pcb.findall(".//fragment/wire"))
    vias_count = len(pcb.findall(".//via"))
    pads_count = len(pcb.findall(".//pad")) + len(pcb.findall(".//rpad"))

    return {
        "version": version,
        "pcb_format": pcb_format,
        "pcb_layers": layers,
        "pcb_traces_count": traces_count,
        "pcb_vias_count": vias_count,
        "pcb_pads_count": pads_count,
    }


def parse_lithium_project(
    *,
    lpr_text: str | None = None,
    lsc_text: str | None = None,
    lbo_text: str | None = None,
) -> LithiumProject:
    """Собрать суммарный отчёт из трёх файлов (любые могут отсутствовать)."""
    if not any([lpr_text, lsc_text, lbo_text]):
        raise LithiumImportError("Не передан ни один Lithium-файл")

    result = LithiumProject()

    if lpr_text:
        try:
            lpr = parse_lpr(lpr_text)
            result.version = lpr["version"]
            result.project_format = lpr["project_format"]
            result.packages = lpr["packages"]
            result.components = lpr["components"]
            result.layers = lpr["layers"]
            result.net_classes = lpr["net_classes"]
        except LithiumImportError as exc:
            result.warnings.append(f".lpr: {exc}")

    if lsc_text:
        try:
            lsc = parse_lsc(lsc_text)
            result.version = result.version or lsc["version"]
            result.schematic_format = lsc["schematic_format"]
            result.erc_rules = lsc["erc_rules"]
            result.cache = lsc["cache"]
            result.pages = lsc["pages"]
            result.nets = lsc["nets"]
            result.ports = lsc["ports"]
        except LithiumImportError as exc:
            result.warnings.append(f".lsc: {exc}")

    if lbo_text:
        try:
            lbo = parse_lbo(lbo_text)
            result.version = result.version or lbo["version"]
            result.pcb_format = lbo["pcb_format"]
            result.pcb_layers = lbo["pcb_layers"]
            result.pcb_traces_count = lbo["pcb_traces_count"]
            result.pcb_vias_count = lbo["pcb_vias_count"]
            result.pcb_pads_count = lbo["pcb_pads_count"]
        except LithiumImportError as exc:
            result.warnings.append(f".lbo: {exc}")

    return result


def detect_lithium_file(filename: str, text: str) -> str:
    """Определить тип файла по имени или содержимому. Возвращает 'lpr'/'lsc'/'lbo' или ''."""
    name = filename.lower()
    if name.endswith(".lpr"):
        return "lpr"
    if name.endswith(".lsc"):
        return "lsc"
    if name.endswith(".lbo"):
        return "lbo"
    head = text[:512]
    if "<project " in head:
        return "lpr"
    if "<schematic " in head:
        return "lsc"
    if "<pcb " in head:
        return "lbo"
    return ""
