"""전략 ③ 입력 데이터를 받아 data/long_stay/outputs/ 에 푼다.

notebooks/7개지역_장기상품_전체분석코드.ipynb 가 읽는 입력 폴더 4개다.
GitHub Release 에서 zip 을 받고, 안쪽 zip 4개를 풀어 같은 이름의 폴더로 둔다.

    python scripts/fetch_strategy3.py                 # Release 에서 내려받기
    python scripts/fetch_strategy3.py --zip 전략3.zip  # 이미 받은 zip 쓰기
"""
import argparse
import io
import shutil
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = ("https://github.com/younghyun729/insight-2026-2/releases/download/"
       "strategy3-data-20261003/strategy3_inputs_20261003.zip")
OUT = ROOT / "data" / "long_stay" / "outputs"


def name_of(info):
    # 맥에서 만든 zip 은 UTF-8 플래그 없이, 자모가 분리된(NFD) 한글 이름을 담는다.
    # 그대로 풀면 이름이 깨지거나 노트북의 경로(NFC)와 맞지 않는다.
    name = info.filename
    if not info.flag_bits & 0x800:
        try:
            name = name.encode("cp437").decode("utf-8")
        except UnicodeError:
            pass
    return unicodedata.normalize("NFC", name)


def extract(z, dest):
    for info in z.infolist():
        name = name_of(info)
        if info.is_dir() or name.startswith("__MACOSX/") or "/._" in name:
            continue
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, help="이미 받은 전략3 zip 경로")
    args = ap.parse_args()

    if args.zip:
        data = args.zip.read_bytes()
    else:
        print("내려받는 중:", URL)
        with urllib.request.urlopen(URL) as r:
            data = r.read()

    OUT.mkdir(parents=True, exist_ok=True)
    outer = zipfile.ZipFile(io.BytesIO(data))
    for info in outer.infolist():
        name = name_of(info)
        if not name.endswith(".zip") or name.startswith("__MACOSX/"):
            continue
        extract(zipfile.ZipFile(io.BytesIO(outer.read(info))), OUT)
        print("풀었음:", Path(name).stem)
    print("완료:", OUT)


if __name__ == "__main__":
    main()
