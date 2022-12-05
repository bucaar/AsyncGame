import asyncio
import collections
import logging

def log(debug: bool, debug_prefix: list[str], name: str, message: str) -> None:
    debug_message = "%s: %s" % (name, message)
    if debug or any(message.startswith(p) for p in debug_prefix):
        logging.debug(debug_message)
    else:
        logging.info(debug_message)

async def readline(name: str, reader: asyncio.StreamReader, buffer: collections.deque[str], *, log_debug: bool = False, log_debug_prefix: list[str] = []) -> str:
    try:
        message = ""
        while buffer:
            message += buffer.popleft()
            for eol in ["\r\n", "\n"]:
                if eol in message:
                    message, extra = message.split(eol, 1)
                    if extra:
                        buffer.appendleft(extra)

                    log(log_debug, log_debug_prefix, "READ (%s)" % name, message)
                    return message

        data = message.encode()
        while data := data + await reader.read(100):
            message = data.decode()
            for eol in ["\r\n", "\n"]:
                if eol in message:
                    message, extra = message.split(eol, 1)
                    if extra:
                        buffer.append(extra)

                    log(log_debug, log_debug_prefix, "READ (%s)" % name, message)
                    return message

    except ConnectionResetError as ex:
        logging.error("STREAMS READ ERROR (%s) - connection reset error" % name, exc_info=ex)
        pass

    if data:
        message = data.decode()
        log(log_debug, log_debug_prefix, "READ (%s)" % name, message)
        return message

async def writeline(name: str, writer: asyncio.StreamWriter, message: str, *, log_debug: bool = False, log_debug_prefix: list[str] = []) -> bool:
    try:
        log(log_debug, log_debug_prefix, "WRITE (%s)" % name, message)

        if not message.endswith("\n"):
            message += "\n"

        if writer.is_closing():
            logging.error("STREAMS WRITE ERROR (%s) - writer is closing" % name)
            return False

        writer.write(message.encode())
        await writer.drain()
        return True

    except ConnectionResetError as ex:
        logging.error("STREAMS WRITE ERROR (%s) - connection reset error" % name, exc_info=ex)
        return False

    except BrokenPipeError as ex:
        logging.error("STREAMS WRITE ERROR (%s) - broken pipe error" % name, exc_info=ex)
        return False