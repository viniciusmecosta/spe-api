import logging
from fastapi_mqtt import FastMQTT, MQTTConfig

from app.core.config import settings

logger = logging.getLogger(__name__)

mqtt_config = MQTTConfig(
    host=settings.MQTT_BROKER,
    port=settings.MQTT_PORT,
    username=settings.MQTT_USERNAME,
    password=settings.MQTT_PASSWORD,
    keepalive=60,
)

mqtt = FastMQTT(config=mqtt_config)


@mqtt.on_connect()
def connect(client, flags, rc, properties):
    logger.info(f"Conectado ao Broker MQTT: {settings.MQTT_BROKER}")


@mqtt.on_disconnect()
def disconnect(client, packet, exc=None):
    logger.warning("Desconectado do Broker MQTT")
