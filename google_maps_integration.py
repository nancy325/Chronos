"""
google_maps_integration.py - Place-search integration using OpenStreetMap.

APIS USED:
  • Nominatim (nominatim.openstreetmap.org) — geocoding & reverse-geocoding
      ↳ Free, 1 request/second rate limit, no API key required
  • Overpass QL (overpass-api.de) — nearby POI discovery
      ↳ Free, distributed across servers, no API key required

INTERFACE:
  The public API (GoogleMapsClient, PlaceResult) maintains compatibility
  with existing codebase, but all calls are backed by OpenStreetMap APIs.

RATE LIMITING:
  • Nominatim: Enforced at 1.05 seconds per request (respectful)
  • Overpass: No per-endpoint limits; queries optimized for speed
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Rate-limiting for Nominatim (max 1 req/sec) ─────────────────────────────
_LAST_NOMINATIM_TS: float = 0.0
_MIN_INTERVAL = 1.05  # seconds between requests

_USER_AGENT = "Chronos/2.1 (OpenStreetMap Nominatim; contact: admin@example.com)"


def _respect_rate_limit() -> None:
    global _LAST_NOMINATIM_TS
    elapsed = time.time() - _LAST_NOMINATIM_TS
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_NOMINATIM_TS = time.time()


# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PlaceResult:
    """A single place returned from the search."""
    name: str
    place_type: str
    rating: float = 0.0          # OSM has no ratings; always 0
    address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    photo_reference: Optional[str] = None


@dataclass
class GeocodingResult:
    """Geocoding result from Nominatim."""
    formatted_address: str
    latitude: float
    longitude: float
    place_id: str = ""
    types: list[str] = field(default_factory=list)


# ── Overpass: OSM tag mapping for activity types ─────────────────────────────
# Maps the same place-type strings used by the pipeline to Overpass tag filters.

_OSM_TAG_MAP: dict[str, str] = {
    "restaurant":          '"amenity"="restaurant"',
    "cafe":                '"amenity"="cafe"',
    "bakery":              '"shop"="bakery"',
    "park":                '"leisure"="park"',
    "garden":              '"leisure"="garden"',
    "nature_reserve":      '"leisure"="nature_reserve"',
    "beach":               '"natural"="beach"',
    "museum":              '"tourism"="museum"',
    "art_gallery":         '"tourism"="gallery"',
    "historical_landmark": '"historic"',
    "shopping_mall":       '"shop"="mall"',
    "store":               '"shop"',
    "amusement_park":      '"leisure"="amusement_park"',
    "ropeways":            '"aerialway"',
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


# ──────────────────────────────────────────────────────────────────────────────
# Client (public interface — kept as GoogleMapsClient for compatibility)
# ──────────────────────────────────────────────────────────────────────────────

class GoogleMapsClient:
    """
    Place-search client backed by OpenStreetMap Nominatim + Overpass APIs.

    INTERFACE COMPATIBILITY:
      The class name is kept as GoogleMapsClient so existing imports
      throughout the project (pipeline.py, etc.) work unchanged.

    ACTUAL IMPLEMENTATION:
      • Geocoding: OpenStreetMap Nominatim
      • Place Discovery: OpenStreetMap Overpass QL
      • Zero API keys required; free tier sufficient for typical usage

    METHODS:
      • search_location(query) → List of possible locations
      • find_nearby_places(lat, lon, types, radius) → List of POIs
    """

    NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"

    def __init__(self, api_key: str | None = None):
        # api_key is accepted but ignored (OSM needs no key)
        pass

    # ── Geocoding (Nominatim) ─────────────────────────────────────────────

    async def geocode(self, address: str) -> Optional[GeocodingResult]:
        """Geocode an address string via Nominatim."""
        params = {
            "q": address,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

        try:
            _respect_rate_limit()
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(self.NOMINATIM_SEARCH, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            if not isinstance(data, list) or not data:
                return None

            top = data[0]
            return GeocodingResult(
                formatted_address=top.get("display_name", address),
                latitude=float(top.get("lat", 0)),
                longitude=float(top.get("lon", 0)),
                place_id=str(top.get("place_id", "")),
                types=[top.get("type", "")],
            )
        except Exception as exc:
            print(f"[OSM Geocode] Error: {exc}")
            return None

    # ── Nearby Place Search (Overpass) ────────────────────────────────────

    async def find_nearby_places(
        self,
        latitude: float,
        longitude: float,
        place_types: list[str],
        radius_meters: int = 5000,
        max_results: int = 10,
    ) -> list[PlaceResult]:
        """
        Search for nearby places via Overpass API.

        Falls back to curated demo data if the query fails.
        """
        # Build a union Overpass query for all requested types
        tag_filters = [_OSM_TAG_MAP[t] for t in place_types if t in _OSM_TAG_MAP]
        if not tag_filters:
            return _demo_nearby_places(place_types, max_results)

        # Construct "around" union query
        node_queries = "\n".join(
            f'  node[{tag}](around:{radius_meters},{latitude},{longitude});'
            for tag in tag_filters
        )
        way_queries = "\n".join(
            f'  way[{tag}](around:{radius_meters},{latitude},{longitude});'
            for tag in tag_filters
        )
        overpass_query = f"""
[out:json][timeout:15];
(
{node_queries}
{way_queries}
);
out center {max_results * 2};
"""

        try:
            async with httpx.AsyncClient(timeout=18.0) as client:
                resp = await client.post(
                    OVERPASS_URL,
                    data={"data": overpass_query},
                    headers={"User-Agent": _USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()

            elements = data.get("elements", [])
            results: list[PlaceResult] = []
            seen_names: set[str] = set()

            for el in elements:
                tags = el.get("tags", {})
                name = tags.get("name")
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                # Resolve coordinates (nodes vs ways with center)
                lat = el.get("lat") or el.get("center", {}).get("lat", 0)
                lon = el.get("lon") or el.get("center", {}).get("lon", 0)

                ptype = (
                    tags.get("amenity")
                    or tags.get("tourism")
                    or tags.get("leisure")
                    or tags.get("shop")
                    or tags.get("natural")
                    or tags.get("historic")
                    or "place"
                )

                addr_parts = [
                    tags.get("addr:street", ""),
                    tags.get("addr:city", ""),
                ]
                address = ", ".join(p for p in addr_parts if p)

                results.append(PlaceResult(
                    name=name,
                    place_type=ptype,
                    rating=0.0,  # OSM has no rating
                    address=address,
                    latitude=float(lat),
                    longitude=float(lon),
                ))

                if len(results) >= max_results:
                    break

            return results if results else _demo_nearby_places(place_types, max_results)

        except Exception as exc:
            print(f"[Overpass Nearby] Error: {exc}")
            return _demo_nearby_places(place_types, max_results)

    # ── Text Search (Nominatim free-text) ─────────────────────────────────

    async def text_search(
        self,
        query: str,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_meters: int = 50000,
    ) -> list[PlaceResult]:
        """Free-text place search via Nominatim."""
        params: dict = {
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "addressdetails": 1,
        }
        if latitude is not None and longitude is not None:
            params["viewbox"] = (
                f"{longitude - 0.5},{latitude + 0.5},"
                f"{longitude + 0.5},{latitude - 0.5}"
            )
            params["bounded"] = 1

        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

        try:
            _respect_rate_limit()
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(self.NOMINATIM_SEARCH, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            results: list[PlaceResult] = []
            for item in data:
                results.append(PlaceResult(
                    name=item.get("name") or item.get("display_name", ""),
                    place_type=item.get("type", ""),
                    address=item.get("display_name", ""),
                    latitude=float(item.get("lat", 0)),
                    longitude=float(item.get("lon", 0)),
                ))
            return results

        except Exception as exc:
            print(f"[OSM TextSearch] Error: {exc}")
            return []


# ──────────────────────────────────────────────────────────────────────────────
# Demo / Fallback Data
# ──────────────────────────────────────────────────────────────────────────────

_DEMO_PLACES: dict[str, list[PlaceResult]] = {
    "restaurant": [
        PlaceResult("The Garden Bistro", "restaurant", 4.5, "Near Main Square"),
        PlaceResult("Spice Route Kitchen", "restaurant", 4.3, "Old City Road"),
    ],
    "cafe": [
        PlaceResult("Blue Sky Café", "cafe", 4.4, "Station Road"),
    ],
    "park": [
        PlaceResult("City Central Park", "park", 4.6, "Downtown"),
        PlaceResult("Riverside Walk", "park", 4.2, "River Bank"),
    ],
    "beach": [
        PlaceResult("Sunset Beach", "beach", 4.7, "Coastal Road"),
    ],
    "museum": [
        PlaceResult("Heritage Museum", "museum", 4.5, "Museum Circle"),
    ],
    "shopping_mall": [
        PlaceResult("Grand Mall", "shopping_mall", 4.1, "Ring Road"),
    ],
}


def _demo_nearby_places(place_types: list[str], max_results: int) -> list[PlaceResult]:
    """Return curated demo places when API calls fail."""
    results: list[PlaceResult] = []
    for ptype in place_types:
        results.extend(_DEMO_PLACES.get(ptype, []))
    return results[:max_results]
