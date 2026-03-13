# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - Unreleased

### Added

- Multi-agent social simulation engine (Twitter/Reddit dual-platform)
- Knowledge graph construction with Zep Cloud integration
- Career/life path simulation with multi-path parallel comparison (P1-P10)
- Report generation with ReACT agent and Zep-integrated search tools
- Industry knowledge RAG pipeline
- Interactive chat interface for simulation exploration
- Vue 3 frontend with D3.js graph visualization
- Docker support with multi-stage builds

### Security

- API key authentication (`MIROFISH_API_KEY`)
- Rate limiting with Flask-Limiter
- Input validation to prevent path traversal
- CORS origin restriction (configurable via `CORS_ORIGINS`)
- DOMPurify XSS protection for rendered content
- Non-root Docker container execution
- Traceback hiding in production mode
- Request body log masking for sensitive fields
