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
- [x] **ユニットテスト**: 設定、動的スキーマ、CLI コマンドのテスト（10 件全パス）
- [ ] **Phase 1: スライド個別解析エンジン (`SlideAnalyzer`)**
- [ ] **Phase 2: コマ割りマッピングエンジン (`SessionMapper`)**
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

---

## 6. テスト実行

```bash
uv run pytest
```
