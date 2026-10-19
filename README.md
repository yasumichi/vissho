# vissho

> 既存の学習資料（スライド画像）から、Ollama 経由の Vision LLM を活用して授業の学習指導案（シラバス・指導案・コマ割り）の作成を支援する CLI ツール

---

## 1. 解決する課題

- **資料と指導案の乖離解消**: 学習資料は随時アップデートされているが、学習指導案が経年変化に対応できておらず乖離している問題を解消します。
- **暗黙知の形式知化**: スライドに明記されていない作成者・教員の補足説明や指導上の留意点を構造化し、他者や将来の自分が再利用できる指導案として文章化します。

---

## 2. 主な特徴

- **3段階処理パイプライン**:
  1. **Phase 1 (個別解析)**: スライド画像を個別に読み込み、概念・キーワード・推定所要時間・補足暗黙知を抽出（画像ハッシュによるキャッシュ対応）。
  2. **Phase 2 (コマ割りマッピング)**: 設定された列定義に基づき動的に JSON スキーマを生成し、Ollama の構造化出力（`format: json`）で各コマに配分。全要素に出典スライド番号を付与しトレーサビリティを担保。
  3. **Phase 3 (全体整合・推敲)**: プログラムによる合計時間・スライド網羅性の厳密な検証と、LLM による授業展開・難易度曲線の推敲。
- **動的スキーマ生成 (Dynamic Schema)**:
  - 出力表の列定義（列名、説明、列幅）を `config.yaml` で自由に変更可能。実行時に Pydantic モデルと Ollama 向け JSON Schema を自動構築。
- **現場に即した Excel 出力**:
  - `openpyxl` による出力（テキスト折り返し、自動列幅調整、時間集計式）。
  - 指定フォーマットやトナー消費に配慮し、**ヘッダー行の背景色や太字装飾を行わないプレーン仕様**。

---

## 3. 現在の実装状況

- [x] **プロジェクト基盤・依存関係管理**: `uv` による Python 3.12 環境、`pyproject.toml`
- [x] **設計仕様書**: [`AGENTS.md`](./AGENTS.md) の策定
- [x] **設定モデル & ローダー**: [`src/vissho/config.py`](./src/vissho/config.py)
  - 前提情報、表の列定義、補足暗黙知の Pydantic モデル定義
  - `config.yaml` の読み込み・保存・初期テンプレート生成
- [x] **動的スキーマ生成エンジン**: [`src/vissho/core/schema.py`](./src/vissho/core/schema.py)
  - 列定義からの動的 `InstructionRow` モデル生成
  - コマ単位（`SessionPlan`）および全体指導案（`CurriculumPlan`）モデル構築
  - Ollama の `format: json` 向け JSON Schema 生成
- [x] **CLI 基盤 & 初期化コマンド**: [`src/vissho/cli.py`](./src/vissho/cli.py)
  - `vissho init`（カレントディレクトリに `config.yaml` の雛形を生成。上書き防止 & `--force` 対応）
- [x] **画像処理 & スライド番号抽出**: [`src/vissho/utils/image.py`](./src/vissho/utils/image.py)
  - ファイル名末尾からのスライド番号自動抽出（`slide_01.png`, `01.png`, `lecture-page-12.png` 等）
  - 画像の SHA-256 ハッシュ計算、画像整合性検証
- [x] **中間キャッシュ機構**: [`src/vissho/utils/cache.py`](./src/vissho/utils/cache.py)
  - 画像ハッシュ・使用モデル・暗黙知補足メモの複合キーによる決定論的キャッシュ管理（`.vissho_cache/`）
- [x] **LLM クライアント & プロンプト**: [`src/vissho/llm/client.py`](./src/vissho/llm/client.py), [`src/vissho/llm/prompts/`](./src/vissho/llm/prompts/)
  - Jinja2 によるスライド解析プロンプト管理（前提条件・暗黙知メモの自動注入）
  - Ollama Vision API 連携アダプタ（構造化 JSON 出力対応）
- [x] **Phase 1: スライド個別解析エンジン (`SlideAnalyzer`)**: [`src/vissho/pipeline/phase1_analyze.py`](./src/vissho/pipeline/phase1_analyze.py)
  - スライド画像からの主題、トピック、重要ポイント、学習活動、所要時間目安、留意点・暗黙知の抽出
  - 差分実行（キャッシュヒット時は推論スキップ）と完全なトレーサビリティ情報の保持
  - CLI コマンド `vissho analyze` による進捗表示（Rich Progress）と結果サマリー表の表示
- [x] **Phase 2: コマ割りマッピングエンジン (`SessionMapper`)**: [`src/vissho/pipeline/phase2_map.py`](./src/vissho/pipeline/phase2_map.py)
  - スライド解析結果を設定（前提条件、コマ数、時間、列定義）に基づき全コマへ教育的・論理的に配分
  - 各行への出典スライド番号（トレーサビリティ）の付与および補足暗黙知の反映
  - 各コマの合計配当時間の決定論的整合性補正（各行の `allocated_minutes` の合算値と同期）
  - CLI コマンド `vissho map` による全コマ指導案テーブル（Rich Table）表示および JSON 出力
- [x] **ユニットテスト**: 全 39 件パス、テストカバレッジ 90%（`phase2_map.py` は 100%）
- [ ] **Phase 3: 全体整合・推敲エンジン (`ConsistencyReviewer`)**
- [ ] **エクスポーター**: Excel (`openpyxl`), Markdown, JSON

---

## 4. セットアップ

### 必要要件
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) (Vision モデル: `llama3.2-vision` 等)

### インストール手順

```bash
# リポジトリのクローン
git clone <repository-url>
cd vissho

# 依存関係の同期（仮想環境の自動作成）
uv sync
```

---

## 5. 使い方

### 5.1 設定ファイルの初期化 (`vissho init`)

カレントディレクトリに `config.yaml` の雛形を生成します。

```bash
uv run vissho init
```

※ 既存の `config.yaml` を上書きしたい場合は `--force` オプションを指定します。

```bash
uv run vissho init --force
```

### 5.2 設定ファイル (`config.yaml`) の構成

```yaml
# vissho 設定ファイル (config.yaml)

# 教育の前提情報
prerequisites:
  purpose: "〇〇技術の基礎概念を理解し、簡単なアプリケーションを自力で構築できる。"
  target_audience: "情報系専門学校 1年生（基礎的なプログラミング知識を有する）"
  prerequisite_knowledge: "Python の基本文法（変数、関数、制御構文）"
  total_sessions: 4       # コマ数
  session_minutes: 90     # 1コマあたりの時間（分）
  rubric:
    - grade: "A"
      criteria: "〇〇の概念を正しく理解し、発展的な課題を独力で解決できる。"
    - grade: "B"
      criteria: "指示に従って基本機能を実装できる。"
    - grade: "C"
      criteria: "基本用語を理解しているが、実装には補助が必要である。"

# 出力する表の列定義
columns:
  - name: "session_number"
    description: "コマ番号（例: 第1コマ）"
    width: 12
  - name: "topic"
    description: "単元・大項目"
    width: 20
  - name: "learning_objectives"
    description: "学生の到達目標・ねらい"
    width: 30
  - name: "activities"
    description: "具体的な学習活動・授業展開"
    width: 40
  - name: "allocated_minutes"
    description: "配当時間（分）"
    width: 12
  - name: "remarks"
    description: "指導上の留意点・準備物・教員の補足説明（暗黙知）"
    width: 30
  - name: "source_slides"
    description: "出典スライド番号一覧"
    width: 16

# 補足・暗黙知の入力（オプション: スライド画像だけでは読み取れない教員の補足説明）
supplementary_notes:
  - slide_number: 5
    note: "ここの図は受講生がつまずきやすいので、板書で具体例を補足して説明する。"
  - slide_number: 12
    note: "時間が押しやすいため、演習課題の一部は持ち帰り宿題としてもよい。"
```

### 5.3 スライドの個別解析 (`vissho analyze`)

指定ディレクトリ内のスライド画像を順次読み込み、各スライドの教育要素（主題、トピック、配当目安時間など）を個別に解析してキャッシュ（`.vissho_cache/`）に保存します。

```bash
uv run vissho analyze slides/
```

主なオプション：
- `-c, --config <path>`: 設定ファイルのパス（デフォルト: `config.yaml`）
- `-m, --model <model>`: 使用する Ollama Vision モデル（デフォルト: `qwen2.5-vl`）
- `-p, --pattern <glob>`: 対象画像のマッチパターン（デフォルト: `*.png`）
- `--no-cache`: 既存キャッシュを無視して強制的に再解析
- `--cache-dir <dir>`: キャッシュ保存先ディレクトリ（デフォルト: `.vissho_cache`）

### 5.4 コマ割りマッピング (`vissho map`)

解析済みのスライド要素を設定ファイル（コマ数、配当時間、出力列定義）に従って全コマに構造化・配分し、各コマの指導案テーブルを表示します。

```bash
# ターミナル上で全コマの指導案テーブルを表示
uv run vissho map slides/

# 生成された構造化カリキュラム指導案を JSON ファイルに保存
uv run vissho map slides/ -o output/curriculum_plan.json
```

主なオプション：
- `-c, --config <path>`: 設定ファイルのパス（デフォルト: `config.yaml`）
- `-m, --model <model>`: 使用する Ollama モデル（デフォルト: `qwen2.5-vl`）
- `-p, --pattern <glob>`: 対象画像のマッチパターン（デフォルト: `*.png`）
- `--cache-dir <dir>`: キャッシュ保存先ディレクトリ（デフォルト: `.vissho_cache`）
- `-o, --output <path>`: 生成されたカリキュラム指導案 JSON の出力先パス

---

## 6. テスト実行

```bash
# 全テスト実行
uv run pytest

# カバレッジ測定
uv run pytest --cov=vissho
```
