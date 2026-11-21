"""Read an accepted provider task without imposing a generation deadline."""
import asyncio
import time

import httpx
import requests


def transient_status(status):
    return status in (408, 425, 429) or isinstance(status, int) and status >= 500


def transient_error(error):
    return isinstance(error, (requests.Timeout, requests.ConnectionError, httpx.TransportError))


def read_status(call):
    while True:
        try:
            result = call()
        except Exception as error:
            if not transient_error(error):
                raise
        else:
            if not transient_status(getattr(result, "status_code", None)):
                return result
        time.sleep(5)


async def read_async_status(call):
    while True:
        try:
            result = await call()
        except Exception as error:
            if not transient_error(error):
                raise
        else:
            if not transient_status(getattr(result, "status_code", None)):
                return result
        await asyncio.sleep(5)
