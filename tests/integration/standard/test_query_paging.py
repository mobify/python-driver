# Copyright 2013-2015 DataStax, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from tests.integration import use_singledc, PROTOCOL_VERSION

import logging
log = logging.getLogger(__name__)

try:
    import unittest2 as unittest
except ImportError:
    import unittest  # noqa

from itertools import cycle, count
from six.moves import range
from threading import Event

from cassandra.cluster import Cluster, PagedResult
from cassandra.concurrent import execute_concurrent, execute_concurrent_with_args
from cassandra.policies import HostDistance
from cassandra.query import SimpleStatement


def setup_module():
    use_singledc()


class QueryPagingTests(unittest.TestCase):

    def setUp(self):
        if PROTOCOL_VERSION < 2:
            raise unittest.SkipTest(
                "Protocol 2.0+ is required for Paging state, currently testing against %r"
                % (PROTOCOL_VERSION,))

        self.cluster = Cluster(protocol_version=PROTOCOL_VERSION)
        if PROTOCOL_VERSION < 3:
            self.cluster.set_core_connections_per_host(HostDistance.LOCAL, 1)
        self.session = self.cluster.connect()
        self.session.execute("TRUNCATE test3rf.test")

    def tearDown(self):
        self.cluster.shutdown()

    def test_paging(self):
        statements_and_params = zip(cycle(["INSERT INTO test3rf.test (k, v) VALUES (%s, 0)"]),
                                    [(i, ) for i in range(100)])
        execute_concurrent(self.session, list(statements_and_params))

        prepared = self.session.prepare("SELECT * FROM test3rf.test")

        for fetch_size in (2, 3, 7, 10, 99, 100, 101, 10000):
            self.session.default_fetch_size = fetch_size
            self.assertEqual(100, len(list(self.session.execute("SELECT * FROM test3rf.test"))))

            statement = SimpleStatement("SELECT * FROM test3rf.test")
            self.assertEqual(100, len(list(self.session.execute(statement))))

            self.assertEqual(100, len(list(self.session.execute(prepared))))

    def test_paging_verify_writes(self):
        statements_and_params = zip(cycle(["INSERT INTO test3rf.test (k, v) VALUES (%s, 0)"]),
                                    [(i, ) for i in range(100)])
        execute_concurrent(self.session, statements_and_params)

        prepared = self.session.prepare("SELECT * FROM test3rf.test")

        for fetch_size in (2, 3, 7, 10, 99, 100, 101, 10000):
            self.session.default_fetch_size = fetch_size
            results = self.session.execute("SELECT * FROM test3rf.test")
            result_array = set()
            result_set = set()
            for result in results:
                result_array.add(result.k)
                result_set.add(result.v)

            self.assertEqual(set(range(100)), result_array)
            self.assertEqual(set([0]), result_set)

            statement = SimpleStatement("SELECT * FROM test3rf.test")
            results = self.session.execute(statement)
            result_array = set()
            result_set = set()
            for result in results:
                result_array.add(result.k)
                result_set.add(result.v)

            self.assertEqual(set(range(100)), result_array)
            self.assertEqual(set([0]), result_set)

            results = self.session.execute(prepared)
            result_array = set()
            result_set = set()
            for result in results:
                result_array.add(result.k)
                result_set.add(result.v)

            self.assertEqual(set(range(100)), result_array)
            self.assertEqual(set([0]), result_set)

    def test_paging_verify_with_composite_keys(self):
        ddl = '''
            CREATE TABLE test3rf.test_paging_verify_2 (
                k1 int,
                k2 int,
                v int,
                PRIMARY KEY(k1, k2)
            )'''
        self.session.execute(ddl)

        statements_and_params = zip(cycle(["INSERT INTO test3rf.test_paging_verify_2 "
                                           "(k1, k2, v) VALUES (0, %s, %s)"]),
                                    [(i, i + 1) for i in range(100)])
        execute_concurrent(self.session, statements_and_params)

        prepared = self.session.prepare("SELECT * FROM test3rf.test_paging_verify_2")

        for fetch_size in (2, 3, 7, 10, 99, 100, 101, 10000):
            self.session.default_fetch_size = fetch_size
            results = self.session.execute("SELECT * FROM test3rf.test_paging_verify_2")
            result_array = []
            value_array = []
            for result in results:
                result_array.append(result.k2)
                value_array.append(result.v)

            self.assertSequenceEqual(range(100), result_array)
            self.assertSequenceEqual(range(1, 101), value_array)

            statement = SimpleStatement("SELECT * FROM test3rf.test_paging_verify_2")
            results = self.session.execute(statement)
            result_array = []
            value_array = []
            for result in results:
                result_array.append(result.k2)
                value_array.append(result.v)

            self.assertSequenceEqual(range(100), result_array)
            self.assertSequenceEqual(range(1, 101), value_array)

            results = self.session.execute(prepared)
            result_array = []
            value_array = []
            for result in results:
                result_array.append(result.k2)
                value_array.append(result.v)

            self.assertSequenceEqual(range(100), result_array)
            self.assertSequenceEqual(range(1, 101), value_array)

    def test_async_paging(self):
        statements_and_params = zip(cycle(["INSERT INTO test3rf.test (k, v) VALUES (%s, 0)"]),
                                    [(i, ) for i in range(100)])
        execute_concurrent(self.session, list(statements_and_params))

        prepared = self.session.prepare("SELECT * FROM test3rf.test")

        for fetch_size in (2, 3, 7, 10, 99, 100, 101, 10000):
            self.session.default_fetch_size = fetch_size
            self.assertEqual(100, len(list(self.session.execute_async("SELECT * FROM test3rf.test").result())))

            statement = SimpleStatement("SELECT * FROM test3rf.test")
            self.assertEqual(100, len(list(self.session.execute_async(statement).result())))

            self.assertEqual(100, len(list(self.session.execute_async(prepared).result())))

    def test_async_paging_verify_writes(self):
        ddl = '''
            CREATE TABLE test3rf.test_async_paging_verify (
                k1 int,
                k2 int,
                v int,
                PRIMARY KEY(k1, k2)
            )'''
        self.session.execute(ddl)

        statements_and_params = zip(cycle(["INSERT INTO test3rf.test_async_paging_verify "
                                           "(k1, k2, v) VALUES (0, %s, %s)"]),
                                    [(i, i + 1) for i in range(100)])
        execute_concurrent(self.session, statements_and_params)

        prepared = self.session.prepare("SELECT * FROM test3rf.test_async_paging_verify")

        for fetch_size in (2, 3, 7, 10, 99, 100, 101, 10000):
            self.session.default_fetch_size = fetch_size
            results = self.session.execute_async("SELECT * FROM test3rf.test_async_paging_verify").result()
            result_array = []
            value_array = []
            for result in results:
                result_array.append(result.k2)
                value_array.append(result.v)

            self.assertSequenceEqual(range(100), result_array)
            self.assertSequenceEqual(range(1, 101), value_array)

            statement = SimpleStatement("SELECT * FROM test3rf.test_async_paging_verify")
            results = self.session.execute_async(statement).result()
            result_array = []
            value_array = []
            for result in results:
                result_array.append(result.k2)
                value_array.append(result.v)

            self.assertSequenceEqual(range(100), result_array)
            self.assertSequenceEqual(range(1, 101), value_array)

            results = self.session.execute_async(prepared).result()
            result_array = []
            value_array = []
            for result in results:
                result_array.append(result.k2)
                value_array.append(result.v)

            self.assertSequenceEqual(range(100), result_array)
            self.assertSequenceEqual(range(1, 101), value_array)

    def test_paging_callbacks(self):
        statements_and_params = zip(cycle(["INSERT INTO test3rf.test (k, v) VALUES (%s, 0)"]),
                                    [(i, ) for i in range(100)])
        execute_concurrent(self.session, list(statements_and_params))

        prepared = self.session.prepare("SELECT * FROM test3rf.test")

        for fetch_size in (2, 3, 7, 10, 99, 100, 101, 10000):
            self.session.default_fetch_size = fetch_size
            future = self.session.execute_async("SELECT * FROM test3rf.test")

            event = Event()
            counter = count()

            def handle_page(rows, future, counter):
                for row in rows:
                    next(counter)

                if future.has_more_pages:
                    future.start_fetching_next_page()
                else:
                    event.set()

            def handle_error(err):
                event.set()
                self.fail(err)

            future.add_callbacks(callback=handle_page, callback_args=(future, counter), errback=handle_error)
            event.wait()
            self.assertEqual(next(counter), 100)

            # simple statement
            future = self.session.execute_async(SimpleStatement("SELECT * FROM test3rf.test"))
            event.clear()
            counter = count()

            future.add_callbacks(callback=handle_page, callback_args=(future, counter), errback=handle_error)
            event.wait()
            self.assertEqual(next(counter), 100)

            # prepared statement
            future = self.session.execute_async(prepared)
            event.clear()
            counter = count()

            future.add_callbacks(callback=handle_page, callback_args=(future, counter), errback=handle_error)
            event.wait()
            self.assertEqual(next(counter), 100)

    def test_concurrent_with_paging(self):
        statements_and_params = zip(cycle(["INSERT INTO test3rf.test (k, v) VALUES (%s, 0)"]),
                                    [(i, ) for i in range(100)])
        execute_concurrent(self.session, list(statements_and_params))

        prepared = self.session.prepare("SELECT * FROM test3rf.test")

        for fetch_size in (2, 3, 7, 10, 99, 100, 101, 10000):
            self.session.default_fetch_size = fetch_size
            results = execute_concurrent_with_args(self.session, prepared, [None] * 10)
            self.assertEqual(10, len(results))
            for (success, result) in results:
                self.assertTrue(success)
                self.assertEqual(100, len(list(result)))

    def test_fetch_size(self):
        """
        Ensure per-statement fetch_sizes override the default fetch size.
        """
        statements_and_params = zip(cycle(["INSERT INTO test3rf.test (k, v) VALUES (%s, 0)"]),
                                    [(i, ) for i in range(100)])
        execute_concurrent(self.session, list(statements_and_params))

        prepared = self.session.prepare("SELECT * FROM test3rf.test")

        self.session.default_fetch_size = 10
        result = self.session.execute(prepared, [])
        self.assertIsInstance(result, PagedResult)

        self.session.default_fetch_size = 2000
        result = self.session.execute(prepared, [])
        self.assertIsInstance(result, list)

        self.session.default_fetch_size = None
        result = self.session.execute(prepared, [])
        self.assertIsInstance(result, list)

        self.session.default_fetch_size = 10

        prepared.fetch_size = 2000
        result = self.session.execute(prepared, [])
        self.assertIsInstance(result, list)

        prepared.fetch_size = None
        result = self.session.execute(prepared, [])
        self.assertIsInstance(result, list)

        prepared.fetch_size = 10
        result = self.session.execute(prepared, [])
        self.assertIsInstance(result, PagedResult)

        prepared.fetch_size = 2000
        bound = prepared.bind([])
        result = self.session.execute(bound, [])
        self.assertIsInstance(result, list)

        prepared.fetch_size = None
        bound = prepared.bind([])
        result = self.session.execute(bound, [])
        self.assertIsInstance(result, list)

        prepared.fetch_size = 10
        bound = prepared.bind([])
        result = self.session.execute(bound, [])
        self.assertIsInstance(result, PagedResult)

        bound.fetch_size = 2000
        result = self.session.execute(bound, [])
        self.assertIsInstance(result, list)

        bound.fetch_size = None
        result = self.session.execute(bound, [])
        self.assertIsInstance(result, list)

        bound.fetch_size = 10
        result = self.session.execute(bound, [])
        self.assertIsInstance(result, PagedResult)

        s = SimpleStatement("SELECT * FROM test3rf.test", fetch_size=None)
        result = self.session.execute(s, [])
        self.assertIsInstance(result, list)

        s = SimpleStatement("SELECT * FROM test3rf.test")
        result = self.session.execute(s, [])
        self.assertIsInstance(result, PagedResult)

        s = SimpleStatement("SELECT * FROM test3rf.test")
        s.fetch_size = None
        result = self.session.execute(s, [])
        self.assertIsInstance(result, list)
