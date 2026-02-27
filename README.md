# Archi Input 🏛️

建築事例を日々インプットするためのローカルWebアプリ。

## セットアップ

```bash
# 1. リポジトリに移動
cd archi-input

# 2. 仮想環境を作成（推奨）
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. 依存パッケージをインストール
pip install -r requirements.txt

# 4. アプリを起動
python app.py
```

ブラウザで **http://127.0.0.1:5000** にアクセス。

## 使い方

| 画面 | 内容 |
|------|------|
| **Inbox** (`/`) | 作品名やURLを追加してDBに保存 |
| **Today** (`/today`) | 毎日3+1件の事例が表示される。メモを書いて保存 |
| **Library** (`/library`) | 全作品の一覧・検索・メモ編集・削除 |

## データ

- SQLite DB: `./data/app.db`
- バックアップは `data/app.db` をコピーするだけでOK
