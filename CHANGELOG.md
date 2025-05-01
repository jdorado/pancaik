# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2024-04-26
### Changed
- Released new version with latest dependencies and improvements

## [0.1.1] - 2024-04-26
### Fixed
- Enforced stricter Twitter API credential checks: now ensures both presence and non-empty values before using `get_async_client`, improving reliability and error handling for all Twitter API operations.

## [0.1.0] - 2025-04-19
### Added
- Initial public release on PyPI
- Core agent framework
- Task scheduling system (cron, interval, one-off)
- MongoDB integration
- Example agent and configuration
- TwitterAgent: Automated agent for composing tweets, replying to mentions, posting from research and followed users, and engaging with Twitter using customizable pipelines and AI models
- Documentation with MkDocs 