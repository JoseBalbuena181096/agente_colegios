"""
CampusRegistry: Single source of truth for campus (plantel) <-> location_id mappings.
Adapted for Colegios San Angel with 3 planteles: Puebla, Poza Rica, Coatzacoalcos.

NOTE: location_id values are placeholders. Replace with actual GHL sub-account IDs
once the GHL accounts for Colegios San Angel are set up.
"""


_CAMPUS_DATA = {
    "SOz5nfbI23Xm9mXC51bI": {
        "name": "Puebla",
        "token_key": "token_csa_puebla",
        "normalized": "puebla",
        "keywords": ["puebla", "pue"],
    },
    "epK2kqk7MkT8t0OBudqP": {
        "name": "Poza Rica",
        "token_key": "token_csa_pozarica",
        "normalized": "pozarica",
        "keywords": ["poza rica", "pozarica", "poza"],
    },
    "UNorB3dhUdmtfbdjMAOc": {
        "name": "Coatzacoalcos",
        "token_key": "token_csa_coatzacoalcos",
        "normalized": "coatzacoalcos",
        "keywords": ["coatzacoalcos", "coatza"],
    },
}


class CampusRegistry:
    """Singleton registry for campus configuration data."""

    def __init__(self):
        self._data = _CAMPUS_DATA
        self._keywords_map: dict[str, str] | None = None
        self._name_to_id: dict[str, str] | None = None

    # --- Lookups by location_id ---

    def get_config(self, location_id: str) -> dict | None:
        """Full config dict for a location_id."""
        return self._data.get(location_id)

    def get_campus_name(self, location_id: str) -> str:
        """Human-readable campus name. Defaults to 'Puebla'."""
        cfg = self._data.get(location_id)
        return cfg["name"] if cfg else "Puebla"

    def get_token_key(self, location_id: str) -> str | None:
        """Env-var key for the GHL auth token."""
        cfg = self._data.get(location_id)
        return cfg["token_key"] if cfg else None

    # --- Lookups by campus name ---

    def get_location_id(self, campus_name: str) -> str | None:
        """Resolve a campus name (case-insensitive) to its location_id."""
        if not campus_name:
            return None
        name_map = self.get_name_to_id_map()
        return name_map.get(campus_name.lower().strip())

    # --- Bulk maps (cached on first call) ---

    def get_keywords_map(self) -> dict[str, str]:
        """keyword -> normalized campus name (e.g. 'coatza' -> 'coatzacoalcos')."""
        if self._keywords_map is None:
            self._keywords_map = {}
            for cfg in self._data.values():
                for kw in cfg["keywords"]:
                    self._keywords_map[kw] = cfg["normalized"]
        return self._keywords_map

    def get_name_to_id_map(self) -> dict[str, str]:
        """Lowercase name/keyword -> location_id."""
        if self._name_to_id is None:
            self._name_to_id = {}
            for loc_id, cfg in self._data.items():
                self._name_to_id[cfg["normalized"]] = loc_id
                self._name_to_id[cfg["name"].lower()] = loc_id
                for kw in cfg["keywords"]:
                    self._name_to_id[kw] = loc_id
        return self._name_to_id

    def get_all_campus_names(self) -> list[str]:
        """List of human-readable campus names."""
        return [cfg["name"] for cfg in self._data.values()]

    def get_all_location_ids(self) -> list[str]:
        """List of all location_ids."""
        return list(self._data.keys())
