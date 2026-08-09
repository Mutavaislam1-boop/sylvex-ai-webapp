import os
import threading
import time
import unittest
from unittest.mock import patch

import db_pool


class FakeConnection:
    closed = 0
    status = db_pool.extensions.STATUS_READY

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = 1


class FakeThreadedPool:
    def __init__(self, minconn, maxconn, dsn):
        self.maximum = maxconn
        self.created = minconn
        self._pool = [FakeConnection() for _ in range(minconn)]
        self._used = {}

    def getconn(self):
        if self._pool:
            connection = self._pool.pop()
        elif self.created < self.maximum:
            connection = FakeConnection()
            self.created += 1
        else:
            raise db_pool.PoolError("connection pool exhausted")
        self._used[id(connection)] = connection
        return connection

    def putconn(self, connection, close=False):
        self._used.pop(id(connection), None)
        if close:
            connection.close()
            self.created -= 1
        else:
            self._pool.append(connection)

    def closeall(self):
        for connection in self._pool + list(self._used.values()):
            connection.close()


class DatabasePoolConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "DB_POOL_MIN_SIZE": "2",
            "DB_POOL_MAX_SIZE": "10",
            "DB_POOL_TIMEOUT_SECONDS": "3",
        })
        self.environment.start()
        self.pool_patch = patch.object(db_pool, "ThreadedConnectionPool", FakeThreadedPool)
        self.pool_patch.start()

    def tearDown(self):
        db_pool.close_db_pool(timeout=1)
        self.pool_patch.stop()
        self.environment.stop()

    def test_one_hundred_waiters_return_every_connection(self):
        errors = []
        peak = 0
        peak_lock = threading.Lock()

        def work():
            nonlocal peak
            try:
                with db_pool.db_connection("mock-postgres"):
                    with peak_lock:
                        peak = max(peak, db_pool._snapshot()["used"])
                    time.sleep(0.01)
            except BaseException as exc:
                errors.append(exc)

        workers = [threading.Thread(target=work) for _ in range(100)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        status = db_pool.db_pool_status()
        self.assertEqual(errors, [])
        self.assertEqual(peak, 10)
        self.assertEqual(status["used"], 0)
        self.assertEqual(status["waiting"], 0)
        self.assertEqual(status["semaphore_available"], 10)

    def test_legacy_close_is_idempotent(self):
        connection = db_pool.db_connect("mock-postgres")
        connection.close()
        connection.close()
        status = db_pool.db_pool_status()
        self.assertEqual(status["used"], 0)
        self.assertEqual(status["semaphore_available"], 10)


if __name__ == "__main__":
    unittest.main()
