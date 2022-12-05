import asyncio
import collections
import logging
from datetime import datetime
import streams_util

async def start_client() -> None:
    reader, writer = await asyncio.open_connection("192.168.99.108", 12345)
    buffer = collections.deque[str]()

    
    success = await streams_util.writeline("Server", writer, "HELLO")
    if not success:
        logging.info("Write was not successful")
    else:
        while True:
            message = await streams_util.readline("Server", reader, buffer, log_debug_prefix=["PING"])
            expected_response, message = parse_server_message(message)

            if message is None:
                logging.info("No message from server")
                break
            
            if message == "quit":
                logging.info("Quit command recieved")
                break
            
            if message == "PING":
                continue

            print(message)

            if expected_response:
                response = input(" > ")
                success = await streams_util.writeline("Server", writer, response)
                if not success:
                    logging.info("Write was not successful")
                    break

    logging.info("Closing the connection")
    writer.close()
    print("The connection has been closed")

def parse_server_message(message: str) -> tuple[bool, str]:
    if message is None:
        return False, None

    if message.startswith("Y: "):
        return True, message[3: ]

    if message.startswith("N: "):
        return False, message[3: ]

    return False, message

def main() -> None:
    asyncio.run(start_client())

if __name__ == "__main__":
    today = datetime.now()
    d = today.strftime("%Y-%m-%d %H:%M:%S")
    logging.basicConfig(filename="log/client %s.log" % d, encoding="utf-8", level=logging.INFO)
    # logging.basicConfig(filename="log/client %s.log" % d, encoding="utf-8", level=logging.DEBUG)
    # logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)
    main()