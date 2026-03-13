<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Logo" width="75%"/>

AI駆動キャリア＆ライフパスシミュレーター
</br>
<em>マルチエージェント技術で未来のキャリアパスを予測</em>

[![GitHub Stars](https://img.shields.io/github/stars/666ghj/MiroFish?style=flat-square&color=DAA520)](https://github.com/666ghj/MiroFish/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/666ghj/MiroFish?style=flat-square)](https://github.com/666ghj/MiroFish/network)
[![Docker](https://img.shields.io/badge/Docker-Build-2496ED?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/)

[English](./README-EN.md) | [中文文档](./README.md) | [日本語](./README-JA.md)

</div>

## ⚡ キャリアシミュレーター

MiroFish キャリアシミュレーターは、マルチエージェント技術を活用してリアルなキャリア・ライフパスをシミュレーションします。プロフィールを入力するだけで、ライフイベント、障壁、成果を含む複数の並列キャリア軌道を生成します。

### 主な機能

- **マルチパスシミュレーション**: 3つのキャリアパスを並列実行し、結果を比較
- **ライフイベントエンジン**: 育児・教育・加齢などキャリア判断に影響するリアルなイベント
- **ブロッカー分析**: 6カテゴリのキャリア障壁を各段階で評価
- **インタラクティブチャット**: 会話型AIでシミュレーション結果を探索
- **比較レポート**: キャリアパスの横並び分析と実用的な洞察

### アーキテクチャ (P1-P10)

| フェーズ | コンポーネント | 説明 |
|---------|-------------|------|
| P1 | ドメインモデル | BaseIdentity（不変）+ CareerState（可変） |
| P2 | AgentStateStore | エージェントライフサイクル状態管理 |
| P3 | PersonaRenderer | 動的システムメッセージ生成 |
| P4 | LifeEventEngine | スケジュール済み＆確率的ライフイベント |
| P5 | BlockerEngine | 6カテゴリのキャリアブロッカー評価 |
| P6-P7 | SimulationLoop | ラウンドベースのシミュレーション制御 |
| P8 | OASIS統合 | ソーシャルシミュレーションプラットフォーム連携 |
| P9 | 単一パス | 完全な単一パスシミュレーション |
| P10 | マルチパス | 並列3パス比較シミュレーター |

## 🚀 クイックスタート

### 前提条件

| ツール | バージョン | 説明 |
|--------|-----------|------|
| **Node.js** | 18+ | フロントエンド実行環境 |
| **Python** | 3.11-3.12 | バックエンド実行環境 |
| **uv** | 最新版 | Pythonパッケージマネージャ |

### セットアップ

```bash
# 環境変数を設定
cp .env.example .env
# .env を編集してAPIキーを設定

# 全依存関係をインストール
npm run setup:all

# 起動
npm run dev
```

**サービスURL:**
- フロントエンド: `http://localhost:3000`
- バックエンド API: `http://localhost:5001`

### 本番環境設定

```env
MIROFISH_API_KEY=your_strong_random_key
CORS_ORIGINS=https://yourdomain.com
FLASK_DEBUG=False
SECRET_KEY=your_strong_secret_key
```

### Docker

```bash
cp .env.example .env
docker compose up -d
```

## 📄 ドキュメント

- [Contributing Guide](./CONTRIBUTING.md)
- [Security Policy](./SECURITY.md)
- [Code of Conduct](./CODE_OF_CONDUCT.md)
- [Changelog](./CHANGELOG.md)

## 📄 謝辞

MiroFish のシミュレーションエンジンは [OASIS](https://github.com/camel-ai/oasis) (CAMEL-AI) により駆動されています。

## 📄 ライセンス

[AGPL-3.0](./LICENSE)
