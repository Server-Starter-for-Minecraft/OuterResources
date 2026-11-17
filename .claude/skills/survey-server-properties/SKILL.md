---
name: survey-server-properties
description: Survey real Minecraft vanilla servers (jar scan + actual launches) for new versions and update serverstarter2/v1/serverProperties.json — the version ranges (from/to), defaults, choices and descriptions of server properties. Use when a new Minecraft release/snapshot is out, when asked to check or update server properties, or when a property seems to appear in the wrong versions.
---

# serverProperties.json の調査と更新

`serverstarter2/v1/serverProperties.json` のプロパティ定義（対応バージョン `from`/`to`・既定値・選択肢・説明文）を、
実際のサーバー（jar の解析と起動）と照合して更新する手順。調査結果は `data/surveyed.json` に蓄積し、
**調査済みのバージョンは再調査せず、新しいバージョンだけを調べる**。

## 方針

- **「実在しないけど設定できる」は許容し、「実在するのに設定できない」は作らない。**
  範囲を絞りきれない場合（下の「交互に並ぶ期間」）は、プロパティが存在するバージョンをすべて含む側に広げる。
- `from` / `to` は、存在する（しない）ことを確認できたときだけ書く。最新版で存在するプロパティに `to` は書かない。
- 範囲は両端を含む。`from` は最初に存在するバージョン、`to` は**最後に存在する**バージョン。
- バージョンの前後は Mojang のマニフェストの並び順（スナップショット・pre・rc の ID も使える）。
- アプリ（ServerStarter2 `src/components/World/Property/propertyDefinitions.ts`）の判定：
  - 非表示になるのは、すべての定義に `from` があり最も古い `from` より前のバージョン、またはすべての定義に `to` があり最も新しい `to` より後のバージョンだけ。**範囲と範囲の間のバージョンは非表示にならない。**
  - 定義の選択：合う最初の定義 → なければ、そのバージョンより前に終わった範囲のうち最も新しい定義 → それもなければ最も古い定義。
- 1.17 より前は、古いリリース（1.16.5 など）がマニフェスト上で新しいスナップショットの後ろに並ぶ。
  ここで存在が入れ替わるプロパティは1つの範囲で正確に表せないため、存在する側に合わせて広げる（例：`require-resource-pack` は 20w45a から）。
- 型はアプリの組み込み定義（ServerStarter2 `src-electron/schema/serverproperty.ts`）と同じにする（違う型の定義は無視される）。
- 詳細なルールはリポジトリの `README.md`「serverProperties.json」を参照。

## 手順

作業用ディレクトリ（`<work>`）にはスクラッチパッドなどリポジトリ外のディレクトリを使う（jar のダウンロード先）。
スクリプトは `python -I` で実行する（このスキルの `scripts/` から）。

1. **ブランチを作る**（`main` へのマージ = 全ユーザーへの公開）。

2. **新しいバージョンを調査する**

   ```bash
   python -I .claude/skills/survey-server-properties/scripts/survey.py --work <work> --new
   ```

   - `data/surveyed.json` の最も新しいバージョンより後に出た、すべてのバージョン（スナップショット含む）を調べる。
   - 各バージョンで、jar の定数からプロパティ名を取り出し（`keys`）、`--initSettings` でサーバーを起動して書き出された `server.properties` を記録する（`launch`）。`--initSettings` は EULA に同意せず、ワールドも生成しない。
   - 1.14 より前のバージョンは `--initSettings` が無く、EULA に同意しないと `server.properties` が書き出されない。
     **ユーザーが EULA への同意を明言した場合に限り** `--eula` を付ける（`eula=true` で起動し、起動後に `stop` する）。
     `--initSettings` で書き出しを省くバージョン（1.17〜1.18.1 のワールド生成のプロパティ）を通常起動で調べるときは、`--eula --full-start` を付ける。
   - 特定のバージョンだけ調べ直すときは `--new` の代わりにバージョン ID を並べる。
   - Java は ServerStarter2 のキャッシュ（`%APPDATA%/ServerStarter2/serverstarter/cache/bin/runtime`）の Mojang ランタイムを使う。
     指定のランタイムが無い場合は、インストール済みでメジャーバージョンが同じか新しい最も近いもの（Java 16 → 17 など）を使う。
     それも無ければ、そのバージョンを ServerStarter2 で一度起動するか、`--runtime` で指定する。
   - 1バージョンあたり 10〜50 秒程度（ダウンロードと起動）。数十バージョン以上なら、バックグラウンドで実行する。

3. **差分を確認する**

   ```bash
   python -I .claude/skills/survey-server-properties/scripts/report.py --work <work> --since <前回調査した最新バージョン>
   ```

   - `HIDDEN BUT EXISTS`：存在するのに非表示になる → **必ず直す**（範囲を広げる）。
   - `DEFAULT MISMATCH`：既定値が違う → 新しい定義（範囲つき）を追加して直す。下の「既知の差」は除く。
   - `SHOWN BUT ABSENT`：存在しないのに表示される → 方針どおり、範囲を表せない短い期間なら許容。
   - `NOT IN JSON`：JSON に無いプロパティ → 表示する価値があれば追加する（説明文・型・既定値・タブを決める）。
   - `TRANSITIONS`：存在・既定値が変わった場所。`unsurveyed N, try X` は間に未調査のバージョンがある印なので、
     `survey.py X` で調べて範囲を絞り、`unsurveyed` が無くなるまで繰り返す（二分探索）。
   - `--since` を外すと全期間を照合する（JSON を編集した後の確認に使う）。

4. **JSON を編集する**

   - 追加されたプロパティ：最初に存在するバージョンを `from` に。既定値・型・選択肢は起動結果（`launch`）に合わせる。
   - 廃止されたプロパティ：最後に存在するバージョンを `to` に。
   - 既定値・選択肢が変わったもの：定義を分け、それぞれに範囲を付ける（新しい定義を先に書く）。
   - 説明文（`ja` / `en-US`）：Minecraft Wiki（en / ja）の server.properties の説明や changelog で確認する。
     効果がはっきりしないものは推測で書かず、そのままにしてユーザーに伝える。
   - 書式：2 スペースのインデント・LF・末尾に改行。Python で編集する場合は
     `json.dumps(d, indent=2, ensure_ascii=False) + "\n"` で書き出すと元の書式と一致する。

5. **検証する**

   - `report.py`（`--since` なし）で `HIDDEN BUT EXISTS` が空で、`DEFAULT MISMATCH` が既知の差だけであること。
   - JSON Schema（CI の `Validate` と同じ）：
     ```bash
     npx --yes -p ajv-cli@5 -p ajv-formats@3 ajv validate --spec=draft2020 --strict=false -c ajv-formats -s serverstarter2/v1/schema/serverProperties.schema.json -d serverstarter2/v1/serverProperties.json
     ```
     node が無い環境では、bun で `ajv@8` と `ajv-formats@3` を入れて `ajv/dist/2020.js` で検証する。
   - ServerStarter2 のリポジトリが手元にあれば、`src-electron/schema/outerResource/serverProperties.ts` の
     `ServerPropertiesResourceV1.safeParse` でアプリのスキーマも満たすことを確認する。

6. **`data/surveyed.json` と JSON を一緒にコミットする**（コミット・PR はユーザーに頼まれてから）。

## 既知の差（直さなくてよいもの）

- `22w13oneblockatatime`：エイプリルフールのスナップショット（1.18.2 からの派生）。`report.py` で除外済み。
- `management-server-secret`：起動ごとにランダムに生成される値（`<random>` として記録）。
- 1.17〜1.18.1 のサーバーは、通常起動でもワールド生成のプロパティ（`level-type`・`generator-settings` など）を書き出さない。
  存在は jar の解析で判定し、既定値は確認できない（`generator-settings` は 21w17a 以降を `{}` としている）。
- 存在の判定（`report.py`）：18w48a（1.14）以降は起動して書き出されたファイルだけで判定する（jar の解析は無関係の文字列、
  例えば 26.4 のゲームルール `pvp` にも一致するため）。それより前のサーバーは読んだキーしか書き出さない
  （`rcon.*` は RCON が有効なときだけ等）ため、jar の解析結果も合わせて判定する。
- 18w48a より前は `difficulty`・`gamemode` が数値、`level-type` が大文字（`DEFAULT`）で書き出される（定義を分けて対応済み）。
- `announce-player-achievements`（1.7.2〜17w17b）・`resource-pack-hash`（14w31a〜1.8.9）：書き出されなくなった後も、
  古い設定ファイルの移行のために jar が読み続ける旧名。`report.py` は起動結果だけで存在を判定する（`MIGRATION_ONLY`）。
- `texture-pack`（〜1.6.4）の説明文（サーバーテクスチャパックの URL）は Wiki に記載が無く、未確認。
- `level-name`：アプリがワールドごとに管理するため JSON に含めない。
- `test-rainbow-chat`：22w19a だけにあった開発用のプロパティ。

## スクリプト

- `scripts/survey.py`：jar の解析と起動を行い、結果を `data/surveyed.json` に追記する（同じバージョンは上書き）。
- `scripts/report.py`：`data/surveyed.json` と JSON をアプリの判定ロジックで照合する。
- `scripts/common.py`：マニフェストの取得・データの読み書き。
- `data/surveyed.json`：バージョンごとの `keys`（jar から見つかったプロパティ名）、`launch`（起動して書き出された値）、`mode`（`initSettings` / `eula` / null）。
  未調査のスナップショットは、前後の調査済みバージョンの二分探索で範囲を確定済み。
