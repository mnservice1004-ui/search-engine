import argparse
import base64
import json
import re
from pathlib import Path


def extract_json_constant(html, constant_name, next_constant):
    pattern = rf"const\s+{constant_name}\s*=\s*(.*?);\s*const\s+{next_constant}\s*="
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        raise RuntimeError(f"{constant_name} 데이터를 찾지 못했습니다.")
    return json.loads(match.group(1))


def save_data_image(data_url, destination):
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise RuntimeError("Base64 이미지가 아닙니다.")
    destination.write_bytes(base64.b64decode(encoded))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="원본 index HTML 경로")
    parser.add_argument("--project", default=".", help="대상 프로젝트 루트")
    args = parser.parse_args()

    source = Path(args.source)
    project = Path(args.project).resolve()
    html = source.read_text(encoding="utf-8")

    tasks = extract_json_constant(html, "TASKS", "MAP_POINTS")
    map_points = extract_json_constant(html, "MAP_POINTS", "KORIYO_RUNNER")

    data_dir = project / "data"
    image_dir = project / "public" / "images"
    data_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "map_points.json").write_text(
        json.dumps(map_points, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for floor in ("1", "2", "3"):
        match = re.search(
            rf'<img\s+alt="{floor}층 배치도"\s+src="(data:image/[^\"]+)"', html
        )
        if not match:
            raise RuntimeError(f"{floor}층 배치도 이미지를 찾지 못했습니다.")
        extension = ".jpg" if "image/jpeg" in match.group(1) else ".png"
        save_data_image(match.group(1), image_dir / f"floor-{floor}{extension}")

    runner = re.search(r'const\s+KORIYO_RUNNER\s*=\s*"(data:image/[^\"]+)"', html)
    if runner:
        save_data_image(runner.group(1), image_dir / "runner.png")

    print(f"업무 {len(tasks)}건을 추출했습니다.")
    print(f"저장 위치: {data_dir}")


if __name__ == "__main__":
    main()
