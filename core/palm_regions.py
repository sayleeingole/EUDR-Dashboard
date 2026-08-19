"""Known palm-oil-producing sub-national areas per country, for the Overview
map. Approximate province/state centroids from public industry sources (MPOB,
GAPKI, USDA FAS) — informational context for where production concentrates,
not surveyed plantation boundaries."""

PALM_REGIONS = {
    "MYS": {"center": [4.2, 108.9], "zoom": 5, "areas": [
        {"name": "Sabah", "lat": 5.9, "lon": 116.7, "note": "Leading palm oil producing state"},
        {"name": "Sarawak", "lat": 2.5, "lon": 113.0, "note": "Rapid expansion; peatland and forest conversion risk"},
        {"name": "Johor", "lat": 2.0, "lon": 103.3, "note": "Established plantations, refining hub"},
        {"name": "Pahang", "lat": 3.8, "lon": 102.5, "note": "Major planted area"},
        {"name": "Perak", "lat": 4.6, "lon": 101.1, "note": "Established plantations"},
    ]},
    "IDN": {"center": [-2.0, 113.5], "zoom": 5, "areas": [
        {"name": "Riau", "lat": 0.5, "lon": 101.4, "note": "Largest palm oil producing province"},
        {"name": "North Sumatra", "lat": 2.5, "lon": 99.0, "note": "Long-established plantations and mills"},
        {"name": "South Sumatra", "lat": -3.0, "lon": 104.0, "note": "Established plantations"},
        {"name": "West Kalimantan", "lat": 0.0, "lon": 111.5, "note": "Deforestation-risk frontier"},
        {"name": "Central Kalimantan", "lat": -1.7, "lon": 113.4, "note": "Deforestation and peatland risk"},
        {"name": "Papua", "lat": -4.0, "lon": 138.0, "note": "Newest expansion frontier, highest deforestation risk"},
    ]},
    "GTM": {"center": [15.2, -90.3], "zoom": 7, "areas": [
        {"name": "Petén", "lat": 16.9, "lon": -90.0, "note": "Highest deforestation risk, near Maya Biosphere Reserve"},
        {"name": "Izabal", "lat": 15.5, "lon": -88.9, "note": "Established plantations, Caribbean coast"},
        {"name": "Suchitepéquez", "lat": 14.5, "lon": -91.4, "note": "Established plantations, Pacific coast"},
        {"name": "Escuintla", "lat": 14.3, "lon": -90.8, "note": "Established plantations, Pacific coast"},
    ]},
    "COL": {"center": [4.5, -74.0], "zoom": 5, "areas": [
        {"name": "Meta", "lat": 3.3, "lon": -73.1, "note": "Largest producing zone, Eastern Plains"},
        {"name": "Magdalena Medio", "lat": 7.0, "lon": -73.9, "note": "Established plantations"},
        {"name": "Nariño", "lat": 1.3, "lon": -77.9, "note": "Pacific/southwest producing zone"},
    ]},
}


def regions_for(iso3):
    return PALM_REGIONS.get(iso3)
