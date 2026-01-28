#!/usr/bin/env python3
"""
Apple Music Integration Router for Anime Production
Handles playlist integration, BPM analysis, and music-sync video generation
"""

import logging
import httpx
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Query, Depends
from pydantic import BaseModel
import asyncio

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/anime/music", tags=["Music Integration"])

# Apple Music service configuration
APPLE_MUSIC_SERVICE_URL = "http://localhost:8316/api/apple-music"

class PlaylistRequest(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None

class MusicSyncRequest(BaseModel):
    playlist_id: str
    project_id: str
    scene_id: Optional[str] = None
    target_bpm: Optional[int] = None
    sync_mode: str = "auto"  # auto, manual, beat_sync

class BPMAnalysisRequest(BaseModel):
    track_id: str
    apple_music_url: str

@router.get("/status")
async def get_music_service_status():
    """Check Apple Music service connection status"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{APPLE_MUSIC_SERVICE_URL}/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "connected",
                    "apple_music_service": data,
                    "capabilities": [
                        "playlist_access",
                        "track_preview",
                        "bpm_analysis",
                        "music_sync_generation"
                    ]
                }
            else:
                return {"status": "error", "message": "Apple Music service unhealthy"}
    except Exception as e:
        logger.error(f"Failed to connect to Apple Music service: {e}")
        return {"status": "disconnected", "message": str(e)}

@router.get("/playlists")
async def get_playlists(
    music_user_token: Optional[str] = Header(None),
    project_id: Optional[str] = Query(None)
):
    """Get user's Apple Music playlists"""
    try:
        if not music_user_token:
            # Return demo playlists for development
            return {
                "data": [
                    {
                        "id": "demo_1",
                        "name": "Anime Soundtrack Collection",
                        "description": "Epic anime music for video production",
                        "trackCount": 24,
                        "isAnimeRelated": True,
                        "artwork": None,
                        "project_linked": project_id if project_id else None
                    },
                    {
                        "id": "demo_2",
                        "name": "Mario Galaxy Inspired",
                        "description": "Space adventure music matching Mario Galaxy theme",
                        "trackCount": 18,
                        "isAnimeRelated": True,
                        "artwork": None,
                        "project_linked": project_id if project_id else None
                    },
                    {
                        "id": "demo_3",
                        "name": "Action Scene Music",
                        "description": "High-energy tracks for action sequences",
                        "trackCount": 32,
                        "isAnimeRelated": True,
                        "artwork": None,
                        "project_linked": None
                    }
                ],
                "demo": True
            }

        # Forward to Apple Music service
        headers = {"Music-User-Token": music_user_token}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{APPLE_MUSIC_SERVICE_URL}/playlists",
                headers=headers,
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()

                # Enhance playlists with anime-related detection
                if "data" in data:
                    for playlist in data["data"]:
                        playlist["isAnimeRelated"] = _is_anime_related(playlist)
                        playlist["project_linked"] = project_id if project_id else None

                return data
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Apple Music service timeout")
    except Exception as e:
        logger.error(f"Failed to get playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/playlists/{playlist_id}/tracks")
async def get_playlist_tracks(
    playlist_id: str,
    music_user_token: Optional[str] = Header(None)
):
    """Get tracks from a specific playlist"""
    try:
        if playlist_id.startswith("demo_"):
            # Return demo tracks
            demo_tracks = {
                "demo_1": [
                    {
                        "id": "track_1",
                        "name": "Gusty Garden Galaxy",
                        "artist": "Nintendo",
                        "album": "Super Mario Galaxy OST",
                        "bpm": 120,
                        "duration_ms": 180000,
                        "preview_url": None
                    },
                    {
                        "id": "track_2",
                        "name": "Bowser Jr. Battle",
                        "artist": "Nintendo",
                        "album": "Super Mario Galaxy OST",
                        "bpm": 140,
                        "duration_ms": 240000,
                        "preview_url": None
                    }
                ],
                "demo_2": [
                    {
                        "id": "track_3",
                        "name": "Space Junk Galaxy",
                        "artist": "Nintendo",
                        "album": "Super Mario Galaxy OST",
                        "bpm": 110,
                        "duration_ms": 200000,
                        "preview_url": None
                    }
                ]
            }
            return {"data": demo_tracks.get(playlist_id, [])}

        if not music_user_token:
            raise HTTPException(status_code=401, detail="Music-User-Token required")

        headers = {"Music-User-Token": music_user_token}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{APPLE_MUSIC_SERVICE_URL}/playlists/{playlist_id}/tracks",
                headers=headers,
                timeout=10.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except Exception as e:
        logger.error(f"Failed to get playlist tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/bpm")
async def analyze_track_bpm(request: BPMAnalysisRequest):
    """Analyze BPM of a specific track"""
    try:
        # Forward to Apple Music service for BPM analysis
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{APPLE_MUSIC_SERVICE_URL}/analyze/bpm",
                json={
                    "track_id": request.track_id,
                    "apple_music_url": request.apple_music_url
                },
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except Exception as e:
        logger.error(f"BPM analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync/generate")
async def generate_music_synced_video(request: MusicSyncRequest):
    """Generate anime video synchronized with music from playlist"""
    try:
        logger.info(f"Generating music-synced video for playlist {request.playlist_id}")

        # Get playlist tracks for BPM information
        playlist_tracks = await get_playlist_tracks(request.playlist_id)
        if not playlist_tracks.get("data"):
            raise HTTPException(status_code=404, detail="No tracks found in playlist")

        # Calculate average BPM or use specific track
        track_bpms = [track.get("bpm", 120) for track in playlist_tracks["data"] if track.get("bpm")]
        avg_bpm = sum(track_bpms) / len(track_bpms) if track_bpms else 120

        # Use target BPM if specified, otherwise use calculated average
        sync_bpm = request.target_bpm or avg_bpm

        # Calculate frame timing based on BPM
        # Standard: 24 fps, sync every beat or half-beat
        fps = 24
        beats_per_second = sync_bpm / 60
        frames_per_beat = fps / beats_per_second

        generation_config = {
            "project_id": request.project_id,
            "scene_id": request.scene_id,
            "sync_mode": request.sync_mode,
            "bpm": sync_bpm,
            "frames_per_beat": frames_per_beat,
            "fps": fps,
            "music_sync": True,
            "playlist_reference": request.playlist_id,
            "generation_type": "music_synchronized_video"
        }

        # Call the video generation service with music sync parameters
        from api.services.video_generation import generate_video_with_music_sync

        job_result = await generate_video_with_music_sync(generation_config)

        return {
            "job_id": job_result["job_id"],
            "status": "started",
            "sync_config": {
                "bpm": sync_bpm,
                "frames_per_beat": frames_per_beat,
                "sync_mode": request.sync_mode
            },
            "message": f"Music-synced video generation started with BPM {sync_bpm}"
        }

    except Exception as e:
        logger.error(f"Music sync generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/playlists")
async def create_anime_playlist(
    request: PlaylistRequest,
    music_user_token: Optional[str] = Header(None)
):
    """Create a new playlist for anime project"""
    try:
        if not music_user_token:
            # Demo mode - just return success
            return {
                "id": f"demo_{len(request.name)}",
                "name": request.name,
                "description": request.description,
                "project_id": request.project_id,
                "created": True,
                "demo": True
            }

        # Forward to Apple Music service
        headers = {"Music-User-Token": music_user_token}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{APPLE_MUSIC_SERVICE_URL}/playlists",
                headers=headers,
                json={
                    "name": request.name,
                    "description": request.description,
                    "project_metadata": {
                        "anime_project_id": request.project_id,
                        "created_by": "tower_anime_production"
                    }
                },
                timeout=10.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except Exception as e:
        logger.error(f"Failed to create playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recommendations/{project_id}")
async def get_music_recommendations(project_id: str):
    """Get music recommendations for anime project based on characters and themes"""
    try:
        # This would integrate with Echo Brain to get project context
        # and recommend music based on characters, themes, scenes

        # For now, return static recommendations based on project
        recommendations = {
            "by_character": [
                {
                    "character": "Mario",
                    "mood": "heroic_adventure",
                    "recommended_bpm": "120-140",
                    "genres": ["orchestral", "adventure", "upbeat"]
                },
                {
                    "character": "Luigi",
                    "mood": "nervous_but_brave",
                    "recommended_bpm": "100-120",
                    "genres": ["playful", "quirky", "building_confidence"]
                }
            ],
            "by_scene_type": [
                {
                    "scene": "action_sequence",
                    "recommended_bpm": "140-160",
                    "energy": "high",
                    "suggestions": ["fast_drums", "orchestral_crescendo", "electronic_elements"]
                },
                {
                    "scene": "emotional_moment",
                    "recommended_bpm": "80-100",
                    "energy": "low_to_medium",
                    "suggestions": ["piano", "strings", "ambient_pads"]
                }
            ],
            "project_theme": "space_adventure",
            "overall_bpm_range": "110-140"
        }

        return recommendations

    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _is_anime_related(playlist: Dict[str, Any]) -> bool:
    """Detect if a playlist is anime-related based on name and description"""
    anime_keywords = [
        'anime', 'soundtrack', 'ost', 'opening', 'ending', 'theme',
        'mario', 'galaxy', 'adventure', 'nintendo', 'game', 'epic',
        'orchestral', 'japanese', 'studio ghibli', 'naruto', 'onepiece'
    ]

    name = (playlist.get("name", "")).lower()
    description = (playlist.get("description", "")).lower()

    return any(keyword in name or keyword in description for keyword in anime_keywords)

# Export router
__all__ = ["router"]