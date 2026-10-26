# テストから各担当フォルダーのファイルを import できるようにする設定
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ルート（common を使うため）と、各担当フォルダーを読み込み先に追加する
for folder in ["", "weather", "pollen", "recommend", "server", "UI"]:
    sys.path.insert(0, str(ROOT / folder))
