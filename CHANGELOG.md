# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-alpha.1] - 2024-05-02
This is a preliminary alpha release that may contain unstable features.

### Added
- Initial alpha release for v0.2.0

## [0.1.2] - 2024-05-01
### Changed
- Updated documentation URL to GitHub Pages (https://jdorado.github.io/pancaik/)
- Improved error handling in Twitter tools with better logging and exit conditions
- Added 'replies' module to Twitter tools exports

### Fixed
- Enhanced data store assertion handling for cases with should_exit flag
- Improved Twitter API credential validation logic
- Modified content retrieval to use warning instead of error for no followed users
- Enhanced tweet indexing with better handling of empty or zero tweet IDs
- Improved error handling in tweet publishing with proper logging

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