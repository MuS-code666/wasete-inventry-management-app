"""アプリのアイコン（bale_planner/assets/app.ico）を生成する。

青い角丸の背景に、積み上げたベール（白い直方体と結束バンド）を描く。
    .venv/Scripts/python installer/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

BLUE = (31, 111, 235, 255)
WHITE = (255, 255, 255, 255)
STRAP = (31, 111, 235, 255)

OUT = Path(__file__).resolve().parent.parent / "bale_planner" / "assets" / "app.ico"


def draw(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=48 * s, fill=BLUE)
    # 3つのベール（下に2つ、上に1つ）
    bales = [(40, 140, 124, 208), (132, 140, 216, 208), (86, 64, 170, 132)]
    for x0, y0, x1, y1 in bales:
        d.rounded_rectangle([x0 * s, y0 * s, x1 * s, y1 * s], radius=8 * s, fill=WHITE)
        for fx in (0.3, 0.7):  # 結束バンド
            x = x0 + (x1 - x0) * fx
            d.rectangle([(x - 4) * s, y0 * s, (x + 4) * s, y1 * s], fill=STRAP)
    return img


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    draw(256).save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
