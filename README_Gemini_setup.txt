花粉対策システム：修正版コードの利用方法

ファイル
- recommend.py       推薦レベル判定、対策文の組み立て、共通JSON形式の返却
- llm_advisor.py     Gemini API連携（外部AI）
- test_recommend.py  pytestによる単体テスト

1. 必要なパッケージ
  python -m pip install -U google-genai pytest

2. Gemini APIキーを環境変数に設定する（Windows PowerShell）
  $env:GEMINI_API_KEY="Google AI Studioで取得したAPIキー"

   コマンドプロンプト（cmd.exe）の場合
  set GEMINI_API_KEY=Google_AI_Studioで取得したAPIキー

   APIキーをコードに直接書き込まないでください。

3. テスト実行
  python -m pytest -q test_recommend.py

4. Geminiを使ってサンプルを実行
  python llm_advisor.py

注意
- test_recommend.py は、元の pytest.py から名前を変更したテストファイルです。
  pytest.py という名前は pytest ライブラリ名と衝突する可能性があるため、
  プロジェクト内に古い pytest.py が残っている場合は別の名前に変更してください。
- Gemini API呼び出しは有効なAPIキーとネットワーク接続が必要です。
  同梱テストは偽のGeminiクライアントを使うため、API料金や実際の通信は発生しません。
- 仕様書に合わせ、入力では day/date、Pollen/pollen、Wind/wind の別表記を受け付け、
  出力 data の項目名は location/date/level/Pollen/weather/Wind/items/reason に統一します。
- Open-Meteoのweather_codeが数値で渡された場合、表示用の日本語天気に変換します。
- 花粉情報そのもののAPI取得処理は、この3ファイルの役割には含めていません。
  データ収集側が花粉APIのレスポンスを仕様に合うPollen文字列やpollen_typesに変換して渡してください。
