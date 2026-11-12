"""Constants for the rademacher integration."""

DOMAIN = "rademacher"

# Configuration options - following Home Assistant naming conventions
CONF_ENABLE_CYCLIC_SCENE_POLLING = "enable_cyclic_scene_polling"
CONF_CREATE_SCENE_ACTIVATION_ENTITIES = "create_scene_activation_entities"
CONF_INCLUDE_NON_EXECUTABLE_SCENES = "include_non_executable_scenes"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SCENE_UPDATE_INTERVAL = "scene_update_interval"
CONF_CREATE_INVERTED_COVER_POSITION = "create_inverted_cover_position"

DEFAULT_UPDATE_INTERVAL = 10  # seconds
DEFAULT_SCENE_UPDATE_INTERVAL = 15  # seconds

# Wall controller (button) polling
CONF_BUTTON_POLL_INTERVAL = "button_poll_interval"

DEFAULT_BUTTON_POLL_INTERVAL = 2.0  # seconds
MIN_BUTTON_POLL_INTERVAL = 0.2  # seconds
MAX_BUTTON_POLL_INTERVAL = 10.0  # seconds
BUTTON_POLL_TIMEOUT = 5  # seconds
BUTTON_POLL_MAX_BACKOFF = 30  # seconds
MIN_UPDATE_TIMEOUT = 3  # seconds

EVENT_BUTTON_PRESSED = f"{DOMAIN}_button_pressed"
