from typing import Callable
from pubsub import pub

from ...domain.contracts.event_bus import EventBus


class PubSubEventBus(EventBus):
    def subscribe(self, channel: str, callback: Callable) -> None:
        pub.subscribe(callback, channel)

    def send(self, channel: str, **kwargs) -> None:
        pub.sendMessage(channel, **kwargs)

    def unsubscribe_all(self) -> None:
        pub.unsubAll()
