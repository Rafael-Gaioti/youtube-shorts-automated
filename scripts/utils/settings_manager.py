import yaml
import json
from pathlib import Path
from typing import Any, Dict


class SettingsManager:
    def __init__(
        self,
        settings_path: str = "config/settings.yaml",
        profiles_path: str = "config/user_profiles.json",
    ):
        self.settings_path = Path(settings_path)
        self.profiles_path = Path(profiles_path)
        self.base_settings = self._load_yaml(self.settings_path)
        self.profiles = self._load_json(self.profiles_path)

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_settings(self, profile_name: str = "recommended") -> Dict[str, Any]:
        """Merges base settings with profile-specific overrides."""
        settings = self.base_settings.copy()

        if profile_name in self.profiles:
            profile = self.profiles[profile_name]

            # Aplicar customizações de legendas
            if "caption_styles" in profile:
                # No settings.yaml original não temos uma seção clara de estilos de legenda,
                # mas os scripts esperam certas variáveis. Vamos injetar o perfil inteiro.
                settings["user_profile"] = profile

            # Aplicar regras de descoberta
            if "discovery_rules" in profile:
                rules = profile["discovery_rules"]
                if "max_duration_sec" in rules:
                    # Sobrescreve o target_duration ou similar se necessário
                    if "cuts_config" not in settings:
                        settings["cuts_config"] = {}
                    settings["cuts_config"]["max_video_duration"] = rules[
                        "max_duration_sec"
                    ]

        return settings


# Singleton instance
settings_manager = SettingsManager()
