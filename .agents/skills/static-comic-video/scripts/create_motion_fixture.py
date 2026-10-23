"""建立独立 TEST_ONLY 混合字卡样片；绝不修改生产内容或伪造用户批准。

从现有 60 秒强调技术夹具派生：仅在这个新测试目录内把两处
关键词视觉覆盖替换成全屏动态字卡，旁白/运镜/FFmpeg 总帧数保持原样。
"""
import argparse
from pathlib import Path
import sys

# 直接通过 Python 文件路径运行时，先加入 Skill 根目录。
SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.create_emphasis_fixture import REPO, build, write
from static_comic.contracts import read_json
from static_comic.motion_cards import empty_plan
from static_comic.project import compile_project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New empty TEST_ONLY directory")
    parser.add_argument("--font", default=str(REPO / "cover-studio/fonts/LXGWWenKai/LXGWWenKai-Regular.ttf"))
    args = parser.parse_args()
    root = Path(args.output).resolve()
    # 基础生成器要求目标为空，并校验本机开源字体内嵌的许可元数据。
    build(root, args.font)
    plan = read_json((root / "input/emphasis_plan.json").read_bytes())
    plan["visual_events"] = [event for event in plan["visual_events"]
                             if event["id"] not in ("VE-004", "VE-007")]
    write(root, "input/emphasis_plan.json", plan)
    script = (root / "input/script.txt").read_bytes()
    text = script.decode("utf-8-sig")
    selected = empty_plan(script)
    values = [
        ("MC-004", "SHOT-004", "talkcraft-number-slab", "300%", 574, 646, "bright"),
        ("MC-007", "SHOT-007", "talkcraft-ink-underline", "水墨", 1110, 1178, "paper"),
    ]
    for cid, sid, recipe, word, start, end, style in values:
        position = text.index(word)
        selected["events"].append({
            "id": cid, "shot_id": sid, "recipe": recipe,
            "script_range": [position, position + len(word)], "text": word,
            "style": style, "source": "manual", "start_frame": start, "end_frame": end,
        })
    write(root, "input/motion_cards.json", selected)
    compiled = compile_project(root, technical_fixture=True, write=True)
    cards = compiled["props"].get("motion_cards", [])
    if compiled["total_frames"] != 1800 or len(cards) != 2:
        raise ValueError("SC-M fixture lost fixed total frames or selected motion cards")
    print(f"SC-M TEST_ONLY fixture compiled: {root}; 1800 frames; {len(cards)} motion cards")
    print("human approval=NOT_RUN; genuine narration/real comic acceptance=NOT_RUN")


if __name__ == "__main__":
    main()
