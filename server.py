import asyncio
import collections
import logging
from pprint import pprint
from typing import AsyncGenerator, Callable
import streams_util
from dataclasses import dataclass, field
import re

@dataclass
class Connection:
    addr: tuple
    name: str
    type: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    buffer: collections.deque[str] = field(default_factory=collections.deque)
    attributes: dict = field(default_factory=dict)

    def is_closed(self) -> bool:
        return self.writer.is_closing()

    def increment_attribute(self, attribute: str, amount: int = 1) -> None:
        if attribute not in self.attributes:
            self.attributes[attribute] = 0

        self.attributes[attribute] += 1

class Server:
    def __init__(self) -> None:
        self.connections: list[Connection] = []
        self.names: dict[str, Connection] = {}
        self.old_attributes: dict[str, dict] = {}
        self.server: asyncio.base_events.Server = None
        self.connection_queue: collections.deque[Connection] = collections.deque()
        self.disconnection_queue: collections.deque[Connection] = collections.deque()

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        name = "%s:%d" % (addr[0], addr[1])

        logging.info("SERVER connected to %s" % name)
        connection = Connection(addr, name, "", reader, writer)

        message = await self.read_message(connection)
        if message is None:
            logging.info("SERVER connection closed while getting initial message")
            return
            
        elif message.startswith("GET /"):
            connection.type = "BROWSER"
            await self.handle_browser_connection(connection, message)
            return
            
        elif message == "HELLO":
            connection.type = "SOCKET"
            await self.handle_hello_connection(connection)
            return

        else:
            logging.error("SERVER connection provided unexpected message: %s" % message)
            return
            
    async def handle_browser_connection(self, connection: Connection, data: str) -> None:
        request = [data]
        while True:
            data = await self.read_message(connection)
            if not data:
                break
            request.append(data)
        
        pprint(request)
        
        await self.send_message(connection, """HTTP/1.0 200 OK\n\n<html><body><h1>Hello World</h1></body></html>""")
        connection.writer.close()

    async def handle_hello_connection(self, connection: Connection):
        while True:
            name = await self.get_response(connection, "What is your name?")
            if name is None:
                logging.info("SERVER connection closed while getting name")
                return

            name = name.strip()
            name = re.sub("[^a-zA-Z0-9]+", "_", name)

            if name == "" or name == "_":
                await self.send_message(connection, "Sorry, you must have letters or numbers in your name")
                continue

            if len(name) < 2:
                await self.send_message(connection, "Sorry, your name must be 2 or more letters")
                continue

            if len(name) > 10:
                await self.send_message(connection, "Sorry, your name must be 10 or fewer letters")
                continue

            if self.name_exists(name):
                await self.send_message(connection, "Sorry, that name is already being used")
                continue

            connection.name = name

            if name in self.old_attributes:
                logging.debug("SERVER %s has previously played, setting existing attributes" % name)
                connection.attributes = self.old_attributes[name]

            break

        self.connections.append(connection)
        self.names[connection.name] = connection
        self.connection_queue.append(connection)

        asyncio.create_task(self.ping_connection(connection))

    def name_exists(self, name: str) -> bool:
        return name in self.names

    async def ping_connection(self, connection: Connection) -> None:
        while True:
            if connection.is_closed():
                logging.info("SERVER ping (%s) cancelled - connection is already closed" % connection.name)
                return
            
            success = await streams_util.writeline(connection.name, connection.writer, "PING", log_debug=True)
            if not success:
                logging.info("SERVER ping (%s) was not successful" % connection.name)
                await self.close_connection(connection)
                return
            
            await asyncio.sleep(2)

    async def close_connection(self, connection: Connection) -> None:
        if not connection.is_closed():
            logging.info("SERVER sending connection close message")
            await self.send_message(connection, "quit")
        
        if connection in self.connections:
            self.connections.remove(connection)
        else:
            logging.warning("SERVER connection not in server connections")

        if connection.name in self.names:
            del self.names[connection.name]
        else:
            logging.warning("SERVER connection name not in server names")
        
        connection.writer.close()

        if connection.attributes:
            self.old_attributes[connection.name] = connection.attributes

        self.disconnection_queue.append(connection)

    def prefix_message(self, message: str, expected_response: bool) -> str:
        if message.startswith("Y: ") or message.startswith("N: "):
            return message
        
        if expected_response:
            return "Y: " + message
        else:
            return "N: " + message

    async def send_message(self, connection: Connection, message: str) -> None:
        if connection.type == "SOCKET":
            message = self.prefix_message(message, False)

        success = await streams_util.writeline(connection.name, connection.writer, message)
        if not success:
            logging.info("SERVER write to %s was not successful" % connection.name)
            await self.close_connection(connection)

    async def read_message(self, connection: Connection) -> str:
        response = await streams_util.readline(connection.name, connection.reader, connection.buffer)

        if response is None:
            logging.info("SERVER no message from %s" % connection.name)
            await self.close_connection(connection)
            return None
        
        if response == "quit":
            logging.info("SERVER quit command recieved from %s" % connection.name)
            await self.close_connection(connection)
            return None

        return response

    async def get_response(self, connection: Connection, prompt: str) -> str:
        if connection.type == "SOCKET":
            prompt = self.prefix_message(prompt, True)
        
        await self.send_message(connection, prompt)
        
        response = await self.read_message(connection)
        return response

    # async def announce_message(self, message: str, connections: list[Connection] = None) -> None:
    #     if connections is None:
    #         connections = self.connections

    #     await asyncio.gather(
    #         *[self.send_message(conn, message) for conn in connections]
    #     )

    # async def get_responses(self, prompt: str, connections: list[Connection] = None):# -> AsyncGenerator[tuple[str, int, Connection], None, None]:
    #     if connections is None:
    #         connections = self.connections
        
    #     task_map: dict[asyncio.Task, tuple[Connection, int]] = {}
    #     tasks: list[asyncio.Task] = []
    #     for i, conn in enumerate(connections):
    #         task = asyncio.create_task(self.get_response(conn, prompt))
    #         tasks.append(task)
    #         task_map[task] = (conn, i)

    #     responses: list[str] = [None for _ in connections]
    #     while tasks:
    #         done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    #         for task in done:
    #             conn, i = task_map[task]
    #             result: str = task.result()
    #             responses[i] = result
    #             logging.info("SERVER response from %s (%d): %r" % (conn.name, i, result))
    #             yield result, i, conn

    #     logging.info("SERVER responses: %r" % responses)

    # async def get_responses_all(self, prompt: str, connections: list[Connection] = None) -> list[str]:
    #     responses_dict: dict[int, str] = {}

    #     async for result, index, connection in self.get_responses(prompt, connections):
    #         responses_dict[index] = result

    #     responses_list = sorted(responses_dict.items())
    #     return [item[1] for item in responses_list]

    async def stop_server(self) -> None:
        logging.debug("SERVER: closing connections")
        await asyncio.gather(
            *[self.close_connection(conn) for conn in self.connections]
        )
        logging.debug("SERVER: connections closed")

        logging.debug("SERVER: stopping server")
        self.server.close()
        logging.debug("SERVER: server stopped")

    async def start_server(self) -> None:
        try:
            self.server = await asyncio.start_server(self.handle_connection, "192.168.99.108", 12345)
        except TimeoutError as ex:
            logging.error("SERVER ERROR start server timeout", exc_info=ex)
            return
        except asyncio.CancelledError as ex:
            logging.warning("SERVER ERROR start server cancelled", exc_info=ex)
            return
        except Exception as ex:
            logging.error("SERVER ERROR server could not be started", exc_info=ex)
            return

        addr = self.server.sockets[0].getsockname() if self.server.sockets else "unknown"
        logging.info("SERVER serving on %s" % (addr,))

        async with self.server:
            try:
                await self.server.serve_forever()
            except asyncio.CancelledError as ex:
                logging.warning("SERVER ERROR server cancelled", exc_info=ex)