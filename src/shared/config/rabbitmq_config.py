"""_summary_
This module provides configuration and utility functions for connecting to a RabbitMQ server
and creating channels with specified queues and exchanges.

Functions:
    get_connection() -> pika.BlockingConnection:
        Establishes and returns a connection to the RabbitMQ server using the provided credentials.
    create_channel(queue_name: str) -> Tuple[pika.channel.Channel, pika.BlockingConnection]:
        Creates a channel, declares an exchange and a queue, binds them together, and returns 
        the channel and connection.
Environment Variables:
    RABBITMQ_HOST: The hostname of the RabbitMQ server.
    RABBITMQ_PORT: The port number of the RabbitMQ server.
    RABBITMQ_USER: The username for RabbitMQ authentication (default: 'admin').
    RABBITMQ_PASSWORD: The password for RabbitMQ authentication (default: 'admin').
Author:
    @TheBarzani
"""

import os
import time
from typing import Tuple
import pika
from dotenv import load_dotenv
load_dotenv()

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT'))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'admin')

def get_connection(retries: int = 12, delay_seconds: int = 5) -> pika.BlockingConnection:
    """
    Establishes a connection to the RabbitMQ server using the provided credentials.
    Retries the connection if the broker is not ready yet.

    Args:
        retries (int): Number of connection attempts.
        delay_seconds (int): Seconds to wait between attempts.

    Returns:
        pika.BlockingConnection: A connection to the RabbitMQ server.
    """
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )

    last_exception = None
    for attempt in range(1, retries + 1):
        try:
            print(f"RabbitMQ connection attempt {attempt}/{retries}...")
            connection = pika.BlockingConnection(params)
            print("RabbitMQ connection successful!")
            return connection
        except Exception as exc:
            last_exception = exc
            print(f"RabbitMQ connection attempt {attempt} failed: {exc}")
            if attempt == retries:
                print(f"All {retries} RabbitMQ connection attempts failed")
                raise
            print(f"Retrying in {delay_seconds} seconds...")
            time.sleep(delay_seconds)

    raise last_exception

def create_channel(queue_name: str) -> Tuple[pika.channel.Channel, pika.BlockingConnection]:
    """
    Creates a channel, declares an exchange and a queue, binds them together, and returns
    the channel and connection.
    Args:
        queue_name (str): The name of the queue and routing key for the exchange.
    Returns:
        Tuple[pika.channel.Channel, pika.BlockingConnection]: A tuple containing the channel
        and connection objects.
    """
    connection = get_connection()
    channel = connection.channel()
    # Declare an exchange
    channel.exchange_declare(exchange="user_order", exchange_type='direct', durable=True)

    # Declare a queue
    channel.queue_declare(queue=queue_name, durable=True)

    # Bind the queue to the exchange with a routing key
    channel.queue_bind(exchange="user_order", queue=queue_name, routing_key=queue_name)

    return channel, connection
