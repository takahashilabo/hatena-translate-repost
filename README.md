# hatena-translate-repost

はてなブログの日本語 Markdown 記事を取得し、Gemini で自然な英語に翻訳して、英語ブログへ新規公開投稿する CLI ツールです。

## 前提

- 元記事は Markdown で書かれていること
- はてなブログの AtomPub API を使えること
- Google AI Studio で Gemini API キーを取得できること
- 実行時のパッケージ管理は uv を使うこと

## セットアップ

```bash
uv sync
cp .env.example .env
```

.env に必要な値を設定してください。

## 環境変数

- SOURCE_HATENA_ID: 元ブログのはてな ID
- SOURCE_BLOG_ID: 元ブログのブログ ID
- SOURCE_API_KEY: 元ブログの API キー
- TARGET_HATENA_ID: 投稿先ブログのはてな ID
- TARGET_BLOG_ID: 投稿先ブログのブログ ID
- TARGET_API_KEY: 投稿先ブログの API キー
- GEMINI_API_KEY: Gemini API キー
- GEMINI_MODEL: 省略可。既定値は gemini-2.5-flash
- REQUEST_TIMEOUT_SECONDS: 省略可。既定値は 60
- STATE_PATH: 省略可。既定値は .hatena-translate-repost/state.json

## 使い方

公開投稿:

```bash
uv run hatena-translate-repost publish 1234567890
```

記事 URL から解決して公開投稿:

```bash
uv run hatena-translate-repost publish https://example.hatenablog.com/entry/2026/04/01/120000
```

dry-run で翻訳結果だけ確認:

```bash
uv run hatena-translate-repost publish 1234567890 --dry-run
```

preview コマンドでも同じことができます。

```bash
uv run hatena-translate-repost preview 1234567890
```

## 動作概要

1. 元ブログから対象エントリーを取得する
2. Markdown を壊さないように Gemini で英訳する
3. 投稿先ブログへ Markdown のまま新規投稿する
4. 同じ元記事の二重投稿を防ぐために状態ファイルへ記録する

## 注意

- publish は既定で即時公開します
- 翻訳内容の確認を先にしたい場合は --dry-run を使ってください
- カテゴリは既定でそのままコピーします
- Markdown 前提です。元記事の content type が Markdown 以外なら処理を止めます
