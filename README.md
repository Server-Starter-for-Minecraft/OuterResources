# OuterResources

ServerStarter2 が起動時に読み込む「外部リソース」を配布するリポジトリです。
ここにある JSON を変更すると、**アプリを更新しなくても**寄付ダイアログの内容やサーバープロパティの定義が切り替わります。

## 配布の仕組み

アプリは `main` ブランチのファイルを次の URL から取得します。

```
https://raw.githubusercontent.com/Server-Starter-for-Minecraft/OuterResources/main/serverstarter2/v{スキーマのバージョン}/{ファイル名}
```

- **`main` へのマージ = 全ユーザーへの公開**です。必ず PR を作り、検証（GitHub Actions の `Validate`）が通ってからマージしてください。
- アプリは起動時に同梱の内容（またはキャッシュ）を表示し、取得でき次第この内容に切り替えます。
- 取得した内容がアプリのスキーマを満たさない場合は使われず、前回の内容（キャッシュ）が表示され続けます。ファイルの一部の要素だけが不正な場合は、その要素だけが無視されます。
- アプリのリリース時のビルドで、その時点の `main` の内容がアプリに同梱されます（配布元に接続できない初回起動時に表示する内容）。

## ファイル一覧

| ファイル                                  | 内容                                                                             |
| ----------------------------------------- | -------------------------------------------------------------------------------- |
| `serverstarter2/v1/donation.json`         | 寄付ダイアログ（とホームページの応援ページ）に表示する寄付サービスの一覧         |
| `serverstarter2/v1/serverProperties.json` | プロパティ画面のタブと、サーバープロパティの定義（型・既定値・選択肢・範囲・説明文・対応バージョン） |
| `serverstarter2/v1/icons/`                | 寄付サービスのアイコンなど、JSON から参照する画像                                |
| `serverstarter2/v1/schema/`               | 各ファイルの JSON Schema（ServerStarter2 のリポジトリで生成したもの）            |

### donation.json

```jsonc
{
  "$schema": "./schema/donation.schema.json",
  "services": [
    {
      "id": "ofuse", // 識別子（重複させない）
      "name": "OFUSE", // サービス名（翻訳しない）
      "url": "https://ofuse.me/…", // 寄付ページ（https のみ）
      "icon": "icons/ofuse.png", // 任意。このファイルからの相対パス・https の URL・data URI
      "color": "#2882A7", // サービス名の文字色（#RRGGBB）
      "description": { "ja": "…", "en-US": "…" },
      "visible": true // false にすると表示しない（準備中のサービス）
    }
  ]
}
```

- 配列の順番がそのまま表示順です。
- アイコンはアプリ側でキャッシュされるため、**画像を差し替えるときはファイル名を変えてください**（同じ名前のままだと、取得済みのユーザーには古い画像が表示され続けます）。

### serverProperties.json

```jsonc
{
  "$schema": "./schema/serverProperties.schema.json",
  // 任意。プロパティ画面のタブ（表示順）。省略するとアプリ内のタブを使う。「その他」はアプリが末尾に加える
  "groups": [
    { "id": "base", "label": { "ja": "基本設定", "en-US": "base settings" } },
    { "id": "generator", "label": { "ja": "ワールド設定", "en-US": "world settings" } }
  ],
  "properties": {
    "level-type": {
      "groups": ["generator"], // 任意。表示するタブの id（複数可）
      "description": { "ja": "…", "en-US": "…" }, // 任意。説明文
      "definitions": [
        // バージョンごとの値の定義（1つ以上）
        {
          "minecraftVersion": { "from": "1.19" }, // 任意。対応バージョン（両端を含む）
          "type": "string", // string / boolean / number
          "default": "minecraft:normal",
          "enum": ["minecraft:normal", "minecraft:flat"]
        },
        {
          "minecraftVersion": { "to": "1.18.2" },
          "type": "string",
          "default": "DEFAULT",
          "enum": ["DEFAULT", "FLAT"]
        }
      ]
    }
  }
}
```

（上の `level-type` の例は書き方の説明用で、実際の値ではありません）

- 数値（`type: "number"`）では `min` / `max` / `step` を指定できます。
- **`from` / `to` は、そのバージョンで存在する（しない）ことを確認できた場合にのみ指定してください。** 指定した範囲の外ではプロパティが表示されなくなります。範囲を書かない側は「存在し続ける」とみなされるため、新しいバージョンへの対応が遅れてもプロパティは消えません。
- ワールドのバージョンに合わせて、次のように定義を選びます。
  - ワールドのバージョンに合う最初の定義を使います。
  - 合う定義がない場合は、そのバージョンより前に終わった範囲のうち最も新しい定義を使います（新しいバージョンへの対応が遅れても、直前の定義が使われ続けます）。すべての範囲より古いバージョンでは、最も古い定義を使います。
  - バージョンの前後関係は、Mojang のバージョン一覧の並び順で判定します。
- 次のバージョンのワールドでは、そのバージョンに存在しないプロパティとして、プロパティ画面に表示されません（server.properties の値はそのまま残ります）。
  - すべての定義に `from` を指定したプロパティ：最も古い `from` より前のバージョン
  - すべての定義に `to` を指定したプロパティ：最も新しい `to` より後のバージョン（上の `level-type` のように、上限のない定義があれば表示され続けます。`to` が ServerStarter2 の知らない新しいバージョンの場合も、上限なしとして扱います）
  - システム設定の「規定プロパティ」など、ワールドに依らない画面ではすべて表示されます。
- タブは `groups` で定義した内容がそのまま使われます。各プロパティの `groups` には、そのタブの `id` を指定します。
  - プロパティの `groups` を省略した場合は、アプリ内の分類（`base` / `player` / `server` / `generator` / `spawning` / `world` / `network` / `rcon-query` / `command` / `resourcepack` / `security`）に従います。
  - 表示中のどのタブにも属さないプロパティは「その他」に表示されます。
- 読み込み時に値を範囲で書き換えることはありません（範囲はプロパティ画面の入力チェックにのみ使われます）。
- ServerStarter2 に元から定義されているプロパティでは、**元の型（string / boolean / number）と異なる定義は無視されます**。
- このファイルに無いプロパティも、アプリ内の定義で表示されます（このファイルからアプリ内のプロパティを消すことはできません）。

## スキーマのバージョン（`v1/`）の方針

- **項目の追加**（新しい任意項目、新しいサービス・プロパティ）は `v1/` のまま行えます。旧バージョンのアプリは知らない項目を無視します。
- **項目の削除・意味の変更・必須項目の追加**など、旧バージョンのアプリが読めなくなる変更は `v2/` を新しく作って行います。リリース済みのアプリが使い続けるため、`v1/` は残して更新を続けてください。

## 編集の手順

1. ブランチを作り、JSON を編集します（VS Code などでは `$schema` により入力補完と検証が効きます）。
2. PR を作り、`Validate` が通ることを確認してからマージします。

### スキーマを変更する場合

スキーマの正本は ServerStarter2 のリポジトリ（`src-electron/schema/outerResource/`）の zod の定義です。

1. ServerStarter2 で zod の定義を変更し、`bun run outer-resources schema` で JSON Schema を更新します。
2. 生成された `src-electron/schema/outerResource/jsonSchema/v{n}/*.schema.json` を、このリポジトリの `serverstarter2/v{n}/schema/` にコピーします。

ServerStarter2 の CI（`network` タグのテスト）は、このリポジトリの配布ファイルがアプリのスキーマを満たすこと、アイコンを取得できること、`schema/` がアプリのスキーマと一致することを定期的に確認しています。
