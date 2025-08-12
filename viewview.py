from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, List, Literal
from urllib.parse import urljoin
from functools import wraps
import requests
from requests.exceptions import RequestException
from seleniumbase import SB
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class StreamPlatformConfig:
    """Configuration for streaming platforms."""
    platform: Literal["twitch", "kick"]
    base_url: str
    username: str
    
    @property
    def stream_url(self) -> str:
        """Generate the full stream URL."""
        return urljoin(self.base_url, self.username)

@dataclass(frozen=True)
class TwitchConfig:
    """Twitch-specific configuration."""
    client_id: str = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Public frontend Client-ID
    live_indicator: str = "isLiveBroadcast"

class StreamViewerException(Exception):
    """Base exception for stream viewer errors."""
    pass

def retry_on_exception(max_attempts: int = 3, wait_seconds: int = 2):
    """Decorator for retrying operations that might fail temporarily."""
    def decorator(func):
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=wait_seconds, min=wait_seconds)
        )
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {str(e)}")
                raise StreamViewerException(f"Failed after {max_attempts} attempts: {str(e)}")
        return wrapper
    return decorator

class StreamViewer:
    """Manages automated viewing of streams on different platforms."""
    
    def __init__(self):
        self.browser: Optional[SB] = None
        self.secondary_browser: Optional[SB] = None

    @retry_on_exception()
    def check_twitch_stream(self, username: str, twitch_config: TwitchConfig) -> bool:
        """
        Check if a Twitch stream is currently live.
        
        Args:
            username: The Twitch username to check
            twitch_config: Twitch configuration settings
            
        Returns:
            bool: True if stream is live, False otherwise
        """
        url = f"https://www.twitch.tv/{username}"
        headers = {"Client-ID": twitch_config.client_id}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return twitch_config.live_indicator in response.text
        except RequestException as e:
            logger.error(f"Failed to check Twitch stream status: {str(e)}")
            return False

    def handle_captcha_and_consent(self, browser: SB, reconnect_time: int = 4):
        """Handle captcha and consent popups."""
        browser.sleep(1)
        browser.uc_gui_click_captcha()
        browser.uc_gui_handle_captcha()
        browser.sleep(reconnect_time)
        
        if browser.is_element_present('button:contains("Accept")'):
            browser.uc_click('button:contains("Accept")', reconnect_time=reconnect_time)

    def watch_stream(self, platform_config: StreamPlatformConfig):
        """
        Watch a stream on the specified platform.
        
        Args:
            platform_config: Configuration for the streaming platform
        """
        try:
            with SB(uc=True, test=True) as self.browser:
                logger.info(f"Attempting to watch stream on {platform_config.platform}")
                self._initialize_stream_viewing(platform_config)
                
                if platform_config.platform == "kick":
                    self._watch_kick_stream(platform_config)
                elif platform_config.platform == "twitch":
                    self._watch_twitch_stream(platform_config)
                
        except Exception as e:
            logger.error(f"Error during stream viewing: {str(e)}")
            raise
        finally:
            self._cleanup()

    def _initialize_stream_viewing(self, platform_config: StreamPlatformConfig):
        """Initialize the stream viewing session."""
        self.browser.uc_open_with_reconnect(platform_config.stream_url, 4)
        self.handle_captcha_and_consent(self.browser)

    def _watch_kick_stream(self, platform_config: StreamPlatformConfig):
        """Handle Kick.com specific stream viewing logic."""
        if self.browser.is_element_visible('#injected-channel-player'):
            self._setup_secondary_viewer(platform_config)
            
            while self.browser.is_element_visible('#injected-channel-player'):
                self.browser.sleep(10)

    def _watch_twitch_stream(self, platform_config: StreamPlatformConfig):
        """Handle Twitch.tv specific stream viewing logic."""
        twitch_config = TwitchConfig()
        if self.check_twitch_stream(platform_config.username, twitch_config):
            self._setup_secondary_viewer(platform_config)

    def _setup_secondary_viewer(self, platform_config: StreamPlatformConfig):
        """Setup a secondary browser instance for viewing."""
        self.secondary_browser = self.browser.get_new_driver(undetectable=True)
        self.secondary_browser.uc_open_with_reconnect(platform_config.stream_url, 5)
        self.handle_captcha_and_consent(self.secondary_browser)

    def _cleanup(self):
        """Cleanup browser instances."""
        if self.secondary_browser:
            self.browser.quit_extra_driver()
            self.secondary_browser = None

def main():
    """Main entry point for the stream viewer."""
    # Example usage
    kick_config = StreamPlatformConfig(
        platform="kick",
        base_url="https://kick.com/",
        username="brutalles"
    )
    
    twitch_config = StreamPlatformConfig(
        platform="twitch",
        base_url="https://www.twitch.tv/",
        username="brutalles"
    )
    
    viewer = StreamViewer()
    
    try:
        # Try Kick first
        viewer.watch_stream(kick_config)
        
        # Then try Twitch if needed
        twitch_checker = TwitchConfig()
        if viewer.check_twitch_stream(twitch_config.username, twitch_checker):
            viewer.watch_stream(twitch_config)
            
    except StreamViewerException as e:
        logger.error(f"Stream viewing failed: {str(e)}")
        
if __name__ == "__main__":
    main()
