# Archived Standalone Service

This directory contains the standalone anime_service.py that was causing port conflicts.

## Archive Date: Sun Nov  2 08:57:25 PM UTC 2025
## Reason: Duplicate service conflict with systemd tower-anime-production.service
## Status: Replaced by production systemd service at /opt/tower-anime-production/api/main.py

The standalone service has been archived to prevent future port 8328 conflicts.
Use the systemd service for all anime generation:

sudo systemctl status tower-anime-production
curl -X POST http://localhost:8328/api/anime/generate

