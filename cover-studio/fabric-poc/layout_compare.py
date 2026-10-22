"""Pillow 与 Fabric.js 同模板几何基准比较，用于确定迁移验收范围。"""

from __future__ import annotations

import json
from pathlib import Path


def compare_from_browser_output(stdout: str, destination: Path) -> dict | None:
    from font_catalog import get_font_by_id
    from renderer import build_text_layers

    marker = "FABRIC_POC_RESULT="
    value = next(
        (line[len(marker):] for line in stdout.splitlines() if line.startswith(marker)), None
    )
    if not value:
        return None
    data = json.loads(value)
    ids = data.get("initialFonts", {})
    fonts = {
        "title": get_font_by_id(ids.get("title", "")),
        "subtitle": get_font_by_id(ids.get("subtitle", "")),
    }
    if not all(fonts.values()):
        return {"error": "字体标识已过期，无法生成旧版基准"}
    positions = data.get("initialPositions", {})
    results = []
    for case in data["pngs"]:
        args = dict(
            title=case["title"], subtitle="存款百万不是结束而是开始",
            account="@封面工坊", ratio=case["ratio"],
            title_font=fonts["title"], subtitle_font=fonts["subtitle"],
        )
        for part in ("title", "subtitle", "account"):
            for axis in ("x", "y"):
                pos = positions.get(part, {}).get(axis)
                if pos is not None:
                    args[part + "_" + axis] = pos
        try:
            layers, metrics = build_text_layers(**args)
        except Exception as exc:
            results.append({"ratio": case["ratio"], "title": case["title"], "error": str(exc)})
            continue
        deviations = {}
        for part in ("title", "subtitle", "account"):
            fabric = case["rects"].get(part)
            if fabric is None:
                continue
            python = layers[part]
            x, y = python["position"]
            im = python["image"]
            deviations[part] = {
                "centerDeltaPx": [
                    round(fabric["x"] + fabric["width"] / 2 - x - im.width / 2, 1),
                    round(fabric["y"] + fabric["height"] / 2 - y - im.height / 2, 1),
                ],
                "widthDeltaPx": round(fabric["width"] - im.width, 1),
                "heightDeltaPx": round(fabric["height"] - im.height, 1),
            }
        results.append({
            "ratio": case["ratio"], "title": case["title"],
            "fabricLines": case["lines"], "pythonLines": metrics["title_lines"],
            "wrapMatches": case["lines"] == metrics["title_lines"],
            "fabricFontSize": case["fontSize"], "pythonFontSize": metrics["title_font_size"],
            "fabricWarnings": case.get("warnings", []),
            "deviations": deviations,
        })
    values = [
        abs(v) for case in results
        for detail in case.get("deviations", {}).values()
        for v in detail["centerDeltaPx"]
    ]
    report = {
        "cases": results, "caseCount": len(results),
        "wrapMismatchCount": sum(row.get("wrapMatches") is False for row in results),
        "maxCenterDeltaPx": max(values, default=0),
        "casesWithWarnings": sum(bool(row.get("fabricWarnings")) for row in results),
        "note": "像素外观和文字排版可能不同；本报告是兼容性验收输入，不表示完全一致。",
    }
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {key: report[key] for key in ("caseCount", "wrapMismatchCount", "maxCenterDeltaPx", "casesWithWarnings")}
