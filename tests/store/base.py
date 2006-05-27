import gc

from storm.properties import get_obj_info
from storm.references import Reference, ReferenceSet
from storm.database import Result
from storm.properties import Int, Str, Property
from storm.expr import Asc, Desc, Select, Func
from storm.kinds import StrKind, IntKind
from storm.store import *

from tests.helper import run_this


class Test(object):
    __table__ = "test", "id"

    id = Int()
    title = Str()

class Other(object):
    __table__ = "other", "id"
    id = Int()
    test_id = Int()
    other_title = Str()
    test = Reference(test_id, Test.id)

class Link(object):
    __table__ = "link", ("test_id", "other_id")
    test_id = Int()
    other_id = Int()

class RefTest(Test):
    other = Reference(Test.id, Other.test_id)

class RefSetTest(Test):
    others = ReferenceSet(Test.id, Other.test_id)

class IndRefSetTest(Test):
    others = ReferenceSet(Test.id, Link.test_id, Link.other_id, Other.id)


class DecorateKind(object):

    def to_python(self, value):
        return "to_py(%s)" % str(value)

    def from_python(self, value):
        return "from_py(%s)" % str(value)

    def to_database(self, value):
        return "to_db(%s)" % str(value)

    def from_database(self, value):
        return "from_db(%s)" % str(value)


class KindTest(Test):
    title = Property(kind=DecorateKind())


class StoreTest(object):

    def setUp(self):
        self.create_database()
        self.drop_tables()
        self.create_tables()
        self.create_sample_data()
        self.create_store()

    def tearDown(self):
        self.drop_store()
        self.drop_sample_data()
        self.drop_tables()
        self.drop_database()

    def create_database(self):
        raise NotImplementedError

    def create_tables(self):
        raise NotImplementedError

    def create_sample_data(self):
        connection = self.database.connect()
        connection.execute("INSERT INTO test VALUES (10, 'Title 30')")
        connection.execute("INSERT INTO test VALUES (20, 'Title 20')")
        connection.execute("INSERT INTO test VALUES (30, 'Title 10')")
        connection.execute("INSERT INTO other VALUES (100, 10, 'Title 300')")
        connection.execute("INSERT INTO other VALUES (200, 20, 'Title 200')")
        connection.execute("INSERT INTO other VALUES (300, 30, 'Title 100')")
        connection.execute("INSERT INTO link VALUES (10, 100)")
        connection.execute("INSERT INTO link VALUES (10, 200)")
        connection.execute("INSERT INTO link VALUES (10, 300)")
        connection.execute("INSERT INTO link VALUES (20, 100)")
        connection.execute("INSERT INTO link VALUES (20, 200)")
        connection.execute("INSERT INTO link VALUES (30, 300)")
        connection.commit()

    def create_store(self):
        self.store = Store(self.database)

    def drop_store(self):
        self.store.rollback()

    def drop_sample_data(self):
        pass

    def drop_tables(self):
        for table in ["test", "other", "link"]:
            connection = self.database.connect()
            try:
                connection.execute("DROP TABLE %s" % table)
                connection.commit()
            except:
                connection.rollback()

    def drop_database(self):
        pass

    def get_items(self):
        # Bypass the store to avoid flushing.
        connection = self.store._connection
        result = connection.execute("SELECT * FROM test ORDER BY id")
        return list(result)

    def get_committed_items(self):
        connection = self.database.connect()
        result = connection.execute("SELECT * FROM test ORDER BY id")
        return list(result)


    def test_execute(self):
        result = self.store.execute("SELECT 1")
        self.assertTrue(isinstance(result, Result))
        self.assertEquals(result.fetch_one(), (1,))
        
        result = self.store.execute("SELECT 1", noresult=True)
        self.assertEquals(result, None)

    def test_execute_params(self):
        result = self.store.execute("SELECT ?", [1])
        self.assertTrue(isinstance(result, Result))
        self.assertEquals(result.fetch_one(), (1,))

    def test_execute_flushes(self):
        obj = self.store.get(Test, 10)
        obj.title = "New Title"

        result = self.store.execute("SELECT title FROM test WHERE id=10")
        self.assertEquals(result.fetch_one(), ("New Title",))

    def test_get(self):
        obj = self.store.get(Test, 10)
        self.assertEquals(obj.id, 10)
        self.assertEquals(obj.title, "Title 30")

        obj = self.store.get(Test, 20)
        self.assertEquals(obj.id, 20)
        self.assertEquals(obj.title, "Title 20")

        obj = self.store.get(Test, 40)
        self.assertEquals(obj, None)

    def test_get_cached(self):
        obj = self.store.get(Test, 10)
        self.assertTrue(self.store.get(Test, 10) is obj)

    def test_wb_get_cached_doesnt_need_connection(self):
        obj = self.store.get(Test, 10)
        connection = self.store._connection
        self.store._connection = None
        self.store.get(Test, 10)
        self.store._connection = connection

    def test_cache_cleanup(self):
        obj = self.store.get(Test, 10)
        obj.taint = True

        del obj
        gc.collect()

        obj = self.store.get(Test, 10)
        self.assertFalse(getattr(obj, "taint", False))

    def test_get_tuple(self):
        class Test(object):
            __table__ = "test", ("title", "id")
            id = Int()
            title = Str()
        obj = self.store.get(Test, ("Title 30", 10))
        self.assertEquals(obj.id, 10)
        self.assertEquals(obj.title, "Title 30")

        obj = self.store.get(Test, ("Title 20", 10))
        self.assertEquals(obj, None)

    def test_of(self):
        obj = self.store.get(Test, 10)
        self.assertEquals(Store.of(obj), self.store)
        self.assertEquals(Store.of(Test()), None)
        self.assertEquals(Store.of(object()), None)

    def test_find_iter(self):
        result = self.store.find(Test)

        lst = [(obj.id, obj.title) for obj in result]
        lst.sort()
        self.assertEquals(lst, [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

    def test_find_from_cache(self):
        obj = self.store.get(Test, 10)
        self.assertTrue(self.store.find(Test, id=10).one() is obj)

    def test_find_expr(self):
        result = self.store.find(Test, Test.id == 20,
                                 Test.title == "Title 20")
        self.assertEquals([(obj.id, obj.title) for obj in result], [
                          (20, "Title 20"),
                         ])

        result = self.store.find(Test, Test.id == 10,
                                 Test.title == "Title 20")
        self.assertEquals([(obj.id, obj.title) for obj in result], [
                         ])

    def test_find_keywords(self):
        result = self.store.find(Test, id=20, title="Title 20")
        self.assertEquals([(obj.id, obj.title) for obj in result], [
                          (20, "Title 20")
                         ])

        result = self.store.find(Test, id=10, title="Title 20")
        self.assertEquals([(obj.id, obj.title) for obj in result], [
                         ])

    def test_find_order_by(self, *args):
        result = self.store.find(Test).order_by(Test.title)
        lst = [(obj.id, obj.title) for obj in result]
        self.assertEquals(lst, [
                          (30, "Title 10"),
                          (20, "Title 20"),
                          (10, "Title 30"),
                         ])

    def test_find_order_asc(self, *args):
        result = self.store.find(Test).order_by(Asc(Test.title))
        lst = [(obj.id, obj.title) for obj in result]
        self.assertEquals(lst, [
                          (30, "Title 10"),
                          (20, "Title 20"),
                          (10, "Title 30"),
                         ])

    def test_find_order_desc(self, *args):
        result = self.store.find(Test).order_by(Desc(Test.title))
        lst = [(obj.id, obj.title) for obj in result]
        self.assertEquals(lst, [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

    def test_find_one(self, *args):
        obj = self.store.find(Test).order_by(Test.title).one()
        self.assertEquals(obj.id, 30)
        self.assertEquals(obj.title, "Title 10")

        obj = self.store.find(Test).order_by(Test.id).one()
        self.assertEquals(obj.id, 10)
        self.assertEquals(obj.title, "Title 30")

        obj = self.store.find(Test, id=40).one()
        self.assertEquals(obj, None)

    def test_find_count(self):
        self.assertEquals(self.store.find(Test).count(), 3)

    def test_find_max(self):
        self.assertEquals(self.store.find(Test).max(Test.id), 30)

    def test_find_min(self):
        self.assertEquals(self.store.find(Test).min(Test.id), 10)

    def test_find_avg(self):
        self.assertEquals(int(self.store.find(Test).avg(Test.id)), 20)

    def test_find_sum(self):
        self.assertEquals(int(self.store.find(Test).sum(Test.id)), 60)

    def test_find_remove(self):
        self.store.find(Test, Test.id == 20).remove()
        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (30, "Title 10"),
                         ])

    def test_find_cached(self):
        obj = self.store.get(Test, 20)
        other = self.store.get(Other, 200)
        self.assertTrue(obj)
        self.assertTrue(other)
        self.assertEquals(self.store.find(Test).cached(), [obj])

    def test_find_cached_where(self):
        obj1 = self.store.get(Test, 10)
        obj2 = self.store.get(Test, 20)
        other = self.store.get(Other, 200)
        self.assertTrue(obj1)
        self.assertTrue(obj2)
        self.assertTrue(other)
        self.assertEquals(self.store.find(Test, title="Title 20").cached(),
                          [obj2])


    def test_add_commit(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                          (40, "Title 40"),
                         ])

    def test_add_rollback_commit(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)
        self.store.rollback()

        self.assertEquals(self.store.get(Test, 3), None)

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])
        
        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

    def test_add_get(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)

        old_obj = obj

        obj = self.store.get(Test, 40)

        self.assertEquals(obj.id, 40)
        self.assertEquals(obj.title, "Title 40")

        self.assertTrue(obj is old_obj)

    def test_add_find(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)

        old_obj = obj

        obj = self.store.find(Test, Test.id == 40).one()

        self.assertEquals(obj.id, 40)
        self.assertEquals(obj.title, "Title 40")

        self.assertTrue(obj is old_obj)

    def test_add_twice(self):
        obj = Test()
        self.store.add(obj)
        self.assertRaises(StoreError, self.store.add, obj)

    def test_add_loaded(self):
        obj = self.store.get(Test, 10)
        self.assertRaises(StoreError, self.store.add, obj)

    def test_add_twice_to_wrong_store(self):
        obj = Test()
        self.store.add(obj)
        self.assertRaises(StoreError, Store(self.database).add, obj)

    def test_add_checkpoints(self):
        obj = Other()
        self.store.add(obj)

        obj.id = 400
        obj.test_id = 40
        obj.other_title = "Title 400"

        self.store.flush()
        self.store.execute("UPDATE other SET other_title='Title 500' "
                           "WHERE id=400")
        obj.test_id = 400

        # When not checkpointing, this flush will set other_title again.
        self.store.flush()
        self.store.reload(obj)
        self.assertEquals(obj.other_title, "Title 500")

    def test_remove_commit(self):
        obj = self.store.get(Test, 20)
        self.store.remove(obj)
        self.assertEquals(Store.of(obj), self.store)
        self.store.flush()
        self.assertEquals(Store.of(obj), self.store)

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (30, "Title 10"),
                         ])
        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

        self.store.commit()
        self.assertEquals(Store.of(obj), None)

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (30, "Title 10"),
                         ])

    def test_remove_rollback_update(self):
        obj = self.store.get(Test, 20)

        self.store.remove(obj)
        self.store.rollback()
        
        obj.title = "Title 200"

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

    def test_remove_flush_rollback_update(self):
        obj = self.store.get(Test, 20)

        self.store.remove(obj)
        self.store.flush()
        self.store.rollback()

        obj.title = "Title 200"

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

    def test_remove_add_update(self):
        obj = self.store.get(Test, 20)

        self.store.remove(obj)
        self.store.add(obj)
        
        obj.title = "Title 200"

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

    def test_remove_flush_add_update(self):
        obj = self.store.get(Test, 20)

        self.store.remove(obj)
        self.store.flush()
        self.store.add(obj)
        
        obj.title = "Title 200"

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

    def test_remove_twice(self):
        obj = self.store.get(Test, 10)
        self.store.remove(obj)
        self.assertRaises(StoreError, self.store.remove, obj)

    def test_remove_unknown(self):
        obj = Test()
        self.assertRaises(StoreError, self.store.remove, obj)

    def test_remove_from_wrong_store(self):
        obj = self.store.get(Test, 20)
        self.assertRaises(StoreError, Store(self.database).remove, obj)

    def test_wb_remove_flush_update_isnt_dirty(self):
        obj = self.store.get(Test, 20)
        self.store.remove(obj)
        self.store.flush()
        
        obj.title = "Title 200"

        self.assertTrue(id(obj) not in self.store._dirty)

    def test_wb_remove_rollback_isnt_dirty_or_ghost(self):
        obj = self.store.get(Test, 20)
        self.store.remove(obj)
        self.store.rollback()

        self.assertTrue(id(obj) not in self.store._dirty)
        self.assertTrue(id(obj) not in self.store._ghosts)

    def test_wb_remove_flush_rollback_isnt_dirty_or_ghost(self):
        obj = self.store.get(Test, 20)
        self.store.remove(obj)
        self.store.flush()
        self.store.rollback()

        self.assertTrue(id(obj) not in self.store._dirty)
        self.assertTrue(id(obj) not in self.store._ghosts)

    def test_add_rollback_not_in_store(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)
        self.store.rollback()

        self.assertEquals(Store.of(obj), None)

    def test_update_flush_commit(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 200"

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])
        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])
        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

    def test_update_flush_reload_rollback(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 200"
        self.store.flush()
        self.store.reload(obj)
        self.store.rollback()
        self.assertEquals(obj.title, "Title 20")

    def test_update_commit(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 200"

        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

    def test_update_commit_twice(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 200"
        self.store.commit()
        obj.title = "Title 2000"
        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (20, "Title 2000"),
                          (30, "Title 10"),
                         ])

    def test_update_checkpoints(self):
        obj = self.store.get(Other, 200)
        obj.other_title = "Title 400"
        self.store.flush()
        self.store.execute("UPDATE other SET other_title='Title 500' "
                           "WHERE id=200")
        obj.test_id = 40
        # When not checkpointing, this flush will set other_title again.
        self.store.flush()
        self.store.reload(obj)
        self.assertEquals(obj.other_title, "Title 500")

    def test_update_primary_key(self):
        obj = self.store.get(Test, 20)
        obj.id = 25

        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (25, "Title 20"),
                          (30, "Title 10"),
                         ])

        # Update twice to see if the notion of primary key for the
        # existent object was updated as well.
        
        obj.id = 27

        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 30"),
                          (27, "Title 20"),
                          (30, "Title 10"),
                         ])

        # Ensure only the right ones are there.

        self.assertTrue(self.store.get(Test, 27) is obj)
        self.assertTrue(self.store.get(Test, 25) is None)
        self.assertTrue(self.store.get(Test, 20) is None)

    def test_update_primary_key_exchange(self):
        obj1 = self.store.get(Test, 10)
        obj2 = self.store.get(Test, 30)

        obj1.id = 40
        self.store.flush()
        obj2.id = 10
        self.store.flush()
        obj1.id = 30

        self.assertTrue(self.store.get(Test, 30) is obj1)
        self.assertTrue(self.store.get(Test, 10) is obj2)

        self.store.commit()

        self.assertEquals(self.get_committed_items(), [
                          (10, "Title 10"),
                          (20, "Title 20"),
                          (30, "Title 30"),
                         ])

    def test_wb_update_not_dirty_after_flush(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 200"

        self.store.flush()

        # If changes get committed even with the notification disabled,
        # it means the dirty flag isn't being cleared.

        self.store._disable_change_notification(obj)

        obj.title = "Title 2000"

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

    def test_update_find(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 200"
        
        result = self.store.find(Test, Test.title == "Title 200")

        self.assertTrue(result.one() is obj)

    def test_update_get(self):
        obj = self.store.get(Test, 20)
        obj.id = 200

        self.assertTrue(self.store.get(Test, 200) is obj)

    def test_add_update(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)

        obj.title = "Title 400"

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                          (40, "Title 400"),
                         ])

    def test_add_remove_add(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)
        self.store.remove(obj)

        self.assertEquals(Store.of(obj), self.store)

        obj.title = "Title 400"

        self.store.add(obj)

        obj.id = 400

        self.store.commit()

        self.assertEquals(Store.of(obj), self.store)

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                          (400, "Title 400"),
                         ])

        self.assertTrue(self.store.get(Test, 400) is obj)

    def test_wb_add_remove_add(self):
        obj = Test()
        self.store.add(obj)
        self.assertTrue(id(obj) in self.store._dirty)
        self.store.remove(obj)
        self.assertTrue(id(obj) not in self.store._dirty)
        self.store.add(obj)
        self.assertTrue(id(obj) in self.store._dirty)
        self.assertTrue(Store.of(obj) is self.store)

    def test_wb_update_remove_add(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 200"

        self.store.remove(obj)
        self.store.add(obj)

        self.assertTrue(id(obj) in self.store._dirty)

    def test_sub_class(self):
        class SubTest(Test):
            title = Int()

        obj = self.store.get(Test, 20)
        obj.title = "20"

        obj1 = self.store.get(Test, 20)
        obj2 = self.store.get(SubTest, 20)

        self.assertEquals(obj1.id, 20)
        self.assertEquals(obj1.title, "20")
        self.assertEquals(obj2.id, 20)
        self.assertEquals(obj2.title, 20)

    def test_join(self):

        class Other(object):
            __table__ = "other", "id"
            id = Int()
            other_title = Str()

        other = Other()
        other.id = 40
        other.other_title = "Title 20"

        self.store.add(other)

        # Add another object with the same title to ensure DISTINCT
        # is in place.

        other = Other()
        other.id = 400
        other.other_title = "Title 20"

        self.store.add(other)

        result = self.store.find(Test, Test.title == Other.other_title)

        self.assertEquals([(obj.id, obj.title) for obj in result], [
                          (20, "Title 20")
                         ])

    def test_sub_select(self):
        obj = self.store.find(Test, Test.id == Select("20")).one()
        self.assertTrue(obj)
        self.assertEquals(obj.id, 20)
        self.assertEquals(obj.title, "Title 20")

    def test_attribute_rollback(self):
        obj = self.store.get(Test, 20)
        obj.some_attribute = 1
        self.store.rollback()
        self.assertEquals(getattr(obj, "some_attribute", None), None)

    def test_attribute_rollback_after_commit(self):
        obj = self.store.get(Test, 20)
        obj.some_attribute = 1
        self.store.commit()
        obj.some_attribute = 2
        self.store.rollback()
        self.assertEquals(getattr(obj, "some_attribute", None), 1)

    def test_cache_has_improper_object(self):
        obj = self.store.get(Test, 20)
        self.store.remove(obj)
        self.store.commit()

        self.store.execute("INSERT INTO test VALUES (20, 'Title 20')")

        self.assertTrue(self.store.get(Test, 20) is not obj)

    def test_cache_has_improper_object_readded(self):
        obj = self.store.get(Test, 20)
        self.store.remove(obj)

        self.store.flush()

        old_obj = obj # Keep a reference.

        obj = Test()
        obj.id = 20
        obj.title = "Readded"
        self.store.add(obj)

        self.store.commit()

        self.assertTrue(self.store.get(Test, 20) is obj)

    def test__load__(self):

        loaded = []

        class MyTest(Test):
            def __init__(self):
                loaded.append("NO!")
            def __load__(self):
                loaded.append((self.id, self.title))
                self.title = "Title 200"
                self.some_attribute = 1

        obj = self.store.get(MyTest, 20)

        self.assertEquals(loaded, [(20, "Title 20")])
        self.assertEquals(obj.title, "Title 200")
        self.assertEquals(obj.some_attribute, 1)

        obj.some_attribute = 2

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 200"),
                          (30, "Title 10"),
                         ])

        self.store.rollback()

        self.assertEquals(obj.title, "Title 20")
        self.assertEquals(getattr(obj, "some_attribute", None), 1)

    def test_retrieve_default_primary_key(self):
        obj = Test()
        obj.title = "Title 40"
        self.store.add(obj)
        self.store.flush()
        self.assertNotEquals(obj.id, None)
        self.assertTrue(self.store.get(Test, obj.id) is obj)

    def test_retrieve_default_value(self):
        obj = Test()
        obj.id = 40
        self.store.add(obj)
        self.store.flush()
        self.assertEquals(obj.title, "Default Title")

    def test_wb_remove_prop_not_dirty(self):
        obj = self.store.get(Test, 20)
        del obj.title
        self.assertTrue(id(obj) not in self.store._dirty)

    def test_flush_with_removed_prop(self):
        obj = self.store.get(Test, 20)
        del obj.title
        self.store.flush()
        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

    def test_flush_with_removed_prop_forced_dirty(self):
        obj = self.store.get(Test, 20)
        del obj.title
        obj.id = 40
        obj.id = 20
        self.store.flush()
        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

    def test_flush_with_removed_prop_really_dirty(self):
        obj = self.store.get(Test, 20)
        del obj.title
        obj.id = 25
        self.store.flush()
        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (25, "Title 20"),
                          (30, "Title 10"),
                         ])

    def test_reload(self):
        obj = self.store.get(Test, 20)
        self.store.execute("UPDATE test SET title='Title 40' WHERE id=20")
        self.assertEquals(obj.title, "Title 20")
        self.store.reload(obj)
        self.assertEquals(obj.title, "Title 40")

    def test_reload_not_changed(self):
        obj = self.store.get(Test, 20)
        self.store.execute("UPDATE test SET title='Title 40' WHERE id=20")
        self.store.reload(obj)
        self.assertFalse(get_obj_info(obj).check_changed())

    def test_reload_new_unflushed(self):
        obj = Test()
        obj.id = 40
        obj.title = "Title 40"
        self.assertRaises(StoreError, self.store.reload, obj)

    def test_reload_removed(self):
        obj = self.store.get(Test, 20)
        self.store.remove(obj)
        self.store.flush()
        self.assertRaises(StoreError, self.store.reload, obj)

    def test_reload_unknown(self):
        obj = self.store.get(Test, 20)
        store = Store(self.database)
        self.assertRaises(StoreError, store.reload, obj)

    def test_wb_reload_not_dirty(self):
        obj = self.store.get(Test, 20)
        obj.title = "Title 40"
        self.store.reload(obj)
        self.assertTrue(id(obj) not in self.store._dirty)

    def test_find_set_empty(self):
        self.store.find(Test, title="Title 20").set()
        obj = self.store.get(Test, 20)
        self.assertEquals(obj.title, "Title 20")

    def test_find_set(self):
        self.store.find(Test, title="Title 20").set(title="Title 40")
        obj = self.store.get(Test, 20)
        self.assertEquals(obj.title, "Title 40")

    def test_find_set_column(self):
        self.store.find(Other, other_title="Title 200").set(test_id=Other.id)
        other = self.store.get(Other, 200)
        self.assertEquals(other.test_id, 200)

    def test_find_set_expr(self):
        self.store.find(Test, title="Title 20").set(Test.title == "Title 40")
        obj = self.store.get(Test, 20)
        self.assertEquals(obj.title, "Title 40")

    def test_find_set_none(self):
        self.store.find(Test, title="Title 20").set(title=None)
        obj = self.store.get(Test, 20)
        self.assertEquals(obj.title, None)

    def test_find_set_expr_column(self):
        self.store.find(Other, id=200).set(Other.test_id == Other.id)
        other = self.store.get(Other, 200)
        self.assertEquals(other.id, 200)
        self.assertEquals(other.test_id, 200)

    def test_find_set_on_cached(self):
        obj1 = self.store.get(Test, 20)
        obj2 = self.store.get(Test, 30)
        self.store.find(Test, id=20).set(id=40)
        self.assertEquals(obj1.id, 40)
        self.assertEquals(obj2.id, 30)

    def test_find_set_expr_on_cached(self):
        other = self.store.get(Other, 200)
        self.store.find(Other, id=200).set(Other.test_id == Other.id)
        self.assertEquals(other.id, 200)
        self.assertEquals(other.test_id, 200)

    def test_find_set_none_on_cached(self):
        obj = self.store.get(Test, 20)
        self.store.find(Test, title="Title 20").set(title=None)
        self.assertEquals(obj.title, None)

    def test_find_set_on_cached_but_removed(self):
        obj1 = self.store.get(Test, 20)
        obj2 = self.store.get(Test, 30)
        self.store.remove(obj1)
        self.store.find(Test, id=20).set(id=40)
        self.assertEquals(obj1.id, 20)
        self.assertEquals(obj2.id, 30)

    def test_find_set_on_cached_unsupported_python_expr(self):
        obj1 = self.store.get(Test, 20)
        obj2 = self.store.get(Test, 30)
        self.store.find(Test, Test.id == Select("20")).set(title="Title 40")
        self.assertEquals(obj1.title, "Title 40")
        self.assertEquals(obj2.title, "Title 10")

    def test_find_set_expr_unsupported(self):
        result = self.store.find(Test, title="Title 20")
        self.assertRaises(StoreError, result.set, Test.title > "Title 40")

    def test_find_set_expr_unsupported_2(self):
        result = self.store.find(Test, title="Title 20")
        self.assertRaises(StoreError, result.set, Test.title == Func())

    def test_reference(self):
        other = self.store.get(Other, 100)
        self.assertTrue(other.test)
        self.assertEquals(other.test.title, "Title 30")

    def test_reference_on_non_primary_key(self):
        self.store.execute("INSERT INTO other VALUES (400, 40, 'Title 30')")
        class MyOther(Other):
            test = Reference(Other.other_title, Test.title)

        other = self.store.get(Other, 400)
        self.assertEquals(other.other_title, "Title 30")
        self.assertEquals(other.test, None)

        myother = self.store.get(MyOther, 400)
        self.assertEquals(myother.other_title, "Title 30")
        self.assertNotEquals(myother.test, None)
        self.assertEquals(myother.test.id, 10)
        self.assertEquals(myother.test.title, "Title 30")

    def test_new_reference(self):
        other = Other()
        other.id = 400
        other.title = "Title 400"
        other.test_id = 10

        self.assertEquals(other.test, None)

        self.store.add(other)

        self.assertTrue(other.test)
        self.assertEquals(other.test.title, "Title 30")

    def test_set_reference(self):
        other = self.store.get(Other, 100)
        self.assertEquals(other.test.id, 10)
        test = self.store.get(Test, 30)
        other.test = test
        self.assertEquals(other.test.id, 30)
        result = self.store.execute("SELECT test_id FROM other WHERE id=100")
        self.assertEquals(result.fetch_one(), (30,))

    def test_reference_on_added(self):
        obj = Test()
        obj.title = "Title 40"
        self.store.add(obj)

        other = Other()
        other.id = 400
        other.other_title = "Title 400"
        other.test = obj
        self.store.add(other)

        self.assertEquals(other.test.id, None)
        self.assertEquals(other.test.title, "Title 40")


        self.store.flush()

        self.assertTrue(other.test.id)
        self.assertEquals(other.test.title, "Title 40")

        result = self.store.execute("SELECT test.title FROM test, other "
                                    "WHERE other.id=400 AND "
                                    "test.id = other.test_id")
        self.assertEquals(result.fetch_one(), ("Title 40",))

    def test_reference_on_added_composed_key(self):
        class Other(object):
            __table__ = "other", "id"
            id = Int()
            test_id = Int()
            other_title = Str()
            test = Reference((test_id, other_title), (Test.id, Test.title))

        obj = Test()
        obj.title = "Title 40"
        self.store.add(obj)

        other = Other()
        other.id = 400
        other.test = obj
        self.store.add(other)

        self.assertEquals(other.test.id, None)
        self.assertEquals(other.test.title, "Title 40")
        self.assertEquals(other.other_title, "Title 40")

        self.store.flush()

        self.assertTrue(other.test.id)
        self.assertEquals(other.test.title, "Title 40")

        result = self.store.execute("SELECT test.title FROM test, other "
                                    "WHERE other.id=400 AND "
                                    "test.id = other.test_id")
        self.assertEquals(result.fetch_one(), ("Title 40",))

    def test_reference_on_added_unlink_on_flush(self):
        obj = Test()
        obj.title = "Title 40"
        self.store.add(obj)

        other = Other()
        other.id = 400
        other.test = obj
        other.other_title = "Title 400"
        self.store.add(other)

        obj.id = 40
        self.assertEquals(other.test_id, 40)
        obj.id = 50
        self.assertEquals(other.test_id, 50)
        obj.id = 60
        self.assertEquals(other.test_id, 60)

        self.store.flush()

        obj.id = 70
        self.assertEquals(other.test_id, 60)

    def test_reference_on_added_unlink_on_flush(self):
        obj = Test()
        obj.title = "Title 40"
        self.store.add(obj)

        other = Other()
        other.id = 400
        other.other_title = "Title 400"
        other.test = obj
        self.store.add(other)

        obj.id = 40
        self.assertEquals(other.test_id, 40)
        obj.id = 50
        self.assertEquals(other.test_id, 50)
        obj.id = 60
        self.assertEquals(other.test_id, 60)

        self.store.flush()

        obj.id = 70
        self.assertEquals(other.test_id, 60)

    def test_reference_on_two_added(self):
        obj1 = Test()
        obj1.title = "Title 40"
        obj2 = Test()
        obj2.title = "Title 40"
        self.store.add(obj1)
        self.store.add(obj2)

        other = Other()
        other.id = 400
        other.other_title = "Title 400"
        other.test = obj1
        other.test = obj2
        self.store.add(other)

        obj1.id = 40
        self.assertEquals(other.test_id, None)
        obj2.id = 50
        self.assertEquals(other.test_id, 50)

    def test_reference_on_added_and_changed_manually(self):
        obj = Test()
        obj.title = "Title 40"
        self.store.add(obj)

        other = Other()
        other.id = 400
        other.other_title = "Title 400"
        other.test = obj
        self.store.add(other)

        other.test_id = 40
        obj.id = 50
        self.assertEquals(other.test_id, 40)

    def test_reference_on_added_composed_key_changed_manually(self):
        class Other(object):
            __table__ = "other", "id"
            id = Int()
            test_id = Int()
            other_title = Str()
            test = Reference((test_id, other_title), (Test.id, Test.title))

        obj = Test()
        obj.title = "Title 40"
        self.store.add(obj)

        other = Other()
        other.id = 400
        other.test = obj
        self.store.add(other)

        other.other_title = "Title 50"

        self.assertEquals(other.test, None)

        obj.id = 40

        self.assertEquals(other.test_id, None)

    def test_back_reference(self):
        class MyTest(Test):
            other = Reference(Test.id, Other.test_id)

        mytest = self.store.get(MyTest, 10)
        self.assertTrue(mytest.other)
        self.assertEquals(mytest.other.other_title, "Title 300")

    def test_back_reference_setting(self):
        class MyTest(Test):
            other = Reference(Test.id, Other.test_id, on_remote=True)

        other = Other()
        other.other_title = "Title 400"
        self.store.add(other)

        mytest = MyTest()
        mytest.other = other
        mytest.title = "Title 40"
        self.store.add(mytest)

        self.store.flush()

        self.assertTrue(mytest.id)
        self.assertEquals(other.test_id, mytest.id)

        result = self.store.execute("SELECT other.other_title "
                                    "FROM test, other "
                                    "WHERE test.id = other.test_id AND "
                                    "test.title = 'Title 40'")
        self.assertEquals(result.fetch_one(), ("Title 400",))

    def test_reference_set(self):
        other = Other()
        other.id = 400
        other.test_id = 20
        other.other_title = "Title 400"
        self.store.add(other)

        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)

        mytest = self.store.get(MyTest, 20)

        items = []
        for obj in mytest.others:
            items.append((obj.id, obj.test_id, obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (200, 20, "Title 200"),
                          (400, 20, "Title 400"),
                         ])

    def test_reference_set_with_added(self):
        other1 = Other()
        other1.id = 400
        other1.other_title = "Title 400"
        other2 = Other()
        other2.id = 500
        other2.other_title = "Title 500"
        self.store.add(other1)
        self.store.add(other2)

        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)

        mytest = MyTest()
        mytest.title = "Title 40"
        self.assertEquals(mytest.others, None)
        self.store.add(mytest)
        mytest.others.add(other1)
        mytest.others.add(other2)

        self.assertEquals(mytest.id, None)
        self.assertEquals(other1.test_id, None)
        self.assertEquals(other2.test_id, None)
        self.assertEquals(list(mytest.others.order_by(Other.id)),
                          [other1, other2])
        self.assertEquals(type(mytest.id), int)
        self.assertEquals(mytest.id, other1.test_id)
        self.assertEquals(mytest.id, other2.test_id)

    def test_reference_set_composed(self):
        other = Other()
        other.id = 400
        other.test_id = 20
        other.other_title = "Title 20"
        self.store.add(other)

        class MyTest(Test):
            others = ReferenceSet((Test.id, Test.title),
                                  (Other.test_id, Other.other_title))

        mytest = self.store.get(MyTest, 20)

        items = []
        for obj in mytest.others:
            items.append((obj.id, obj.test_id, obj.other_title))

        self.assertEquals(items, [
                          (400, 20, "Title 20"),
                         ])

        obj = self.store.get(Other, 200)
        obj.other_title = "Title 20"

        del items[:]
        for obj in mytest.others:
            items.append((obj.id, obj.test_id, obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (200, 20, "Title 20"),
                          (400, 20, "Title 20"),
                         ])

    def test_reference_set_find(self):
        other = Other()
        other.id = 400
        other.test_id = 20
        other.other_title = "Title 300"
        self.store.add(other)

        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)

        mytest = self.store.get(MyTest, 20)

        items = []
        for obj in mytest.others.find():
            items.append((obj.id, obj.test_id, obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (200, 20, "Title 200"),
                          (400, 20, "Title 300"),
                         ])

        # Notice that there's another item with this title in the base,
        # which isn't part of the reference.

        objects = list(mytest.others.find(Other.other_title == "Title 300"))
        self.assertEquals(len(objects), 1)
        self.assertTrue(objects[0] is other)

        objects = list(mytest.others.find(other_title="Title 300"))
        self.assertEquals(len(objects), 1)
        self.assertTrue(objects[0] is other)

    def test_reference_set_clear(self):
        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)
        mytest = self.store.get(MyTest, 20)
        mytest.others.clear()
        self.assertEquals(list(mytest.others), [])

    def test_reference_set_clear_cached(self):
        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)
        mytest = self.store.get(MyTest, 20)
        other = self.store.get(Other, 200)
        self.assertEquals(other.test_id, 20)
        mytest.others.clear()
        self.assertEquals(other.test_id, None)

    def test_reference_set_count(self):
        other = Other()
        other.id = 400
        other.test_id = 20
        other.other_title = "Title 400"
        self.store.add(other)

        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)

        mytest = self.store.get(MyTest, 20)

        self.assertEquals(mytest.others.count(), 2)

    def test_reference_set_order_by(self):
        other = Other()
        other.id = 400
        other.test_id = 20
        other.other_title = "Title 100"
        self.store.add(other)

        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)

        mytest = self.store.get(MyTest, 20)

        items = []
        for obj in mytest.others.order_by(Other.id):
            items.append((obj.id, obj.test_id, obj.other_title))
        self.assertEquals(items, [
                          (200, 20, "Title 200"),
                          (400, 20, "Title 100"),
                         ])

        del items[:]
        for obj in mytest.others.order_by(Other.other_title):
            items.append((obj.id, obj.test_id, obj.other_title))
        self.assertEquals(items, [
                          (400, 20, "Title 100"),
                          (200, 20, "Title 200"),
                         ])

    def test_reference_set_remove(self):
        other = Other()
        other.id = 400
        other.test_id = 20
        other.other_title = "Title 100"
        self.store.add(other)

        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)

        mytest = self.store.get(MyTest, 20)
        for obj in mytest.others:
            mytest.others.remove(obj)

        self.assertEquals(other.test_id, None)
        self.assertEquals(list(mytest.others), [])

    def test_reference_set_add(self):
        other = Other()
        other.id = 400
        other.other_title = "Title 100"
        self.store.add(other)

        class MyTest(Test):
            others = ReferenceSet(Test.id, Other.test_id)

        mytest = self.store.get(MyTest, 20)
        mytest.others.add(other)
        self.assertEquals(other.test_id, 20)

    def test_indirect_reference_set(self):
        obj = self.store.get(IndRefSetTest, 20)

        items = []
        for ref_obj in obj.others:
            items.append((ref_obj.id, ref_obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (100, "Title 300"),
                          (200, "Title 200"),
                         ])

    def test_indirect_reference_set_with_added(self):
        other1 = Other()
        other1.id = 400
        other1.other_title = "Title 400"
        other2 = Other()
        other2.id = 500
        other2.other_title = "Title 500"
        self.store.add(other1)
        self.store.add(other2)

        obj = IndRefSetTest()
        obj.title = "Title 40"
        self.assertEquals(obj.id, None)
        self.assertEquals(obj.others, None)
        self.store.add(obj)
        obj.others.add(other1)
        obj.others.add(other2)

        self.assertEquals(obj.id, None)
        self.assertEquals(other1.test_id, None)
        self.assertEquals(other2.test_id, None)
        self.assertEquals(list(obj.others.order_by(Other.id)),
                          [other1, other2])
        self.assertEquals(type(obj.id), int)
        self.assertEquals(type(other1.id), int)
        self.assertEquals(type(other2.id), int)

    def test_indirect_reference_set_find(self):
        obj = self.store.get(IndRefSetTest, 20)

        items = []
        for ref_obj in obj.others.find(Other.other_title == "Title 300"):
            items.append((ref_obj.id, ref_obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (100, "Title 300"),
                         ])

    def test_indirect_reference_set_clear(self):
        obj = self.store.get(IndRefSetTest, 20)
        obj.others.clear()
        self.assertEquals(list(obj.others), [])

    def test_indirect_reference_set_count(self):
        obj = self.store.get(IndRefSetTest, 20)
        self.assertEquals(obj.others.count(), 2)

    def test_indirect_reference_set_order_by(self):
        obj = self.store.get(IndRefSetTest, 20)

        items = []
        for ref_obj in obj.others.order_by(Other.other_title):
            items.append((ref_obj.id, ref_obj.other_title))

        self.assertEquals(items, [
                          (200, "Title 200"),
                          (100, "Title 300"),
                         ])

        del items[:]
        for ref_obj in obj.others.order_by(Other.id):
            items.append((ref_obj.id, ref_obj.other_title))

        self.assertEquals(items, [
                          (100, "Title 300"),
                          (200, "Title 200"),
                         ])

    def test_indirect_reference_set_add(self):
        obj = self.store.get(IndRefSetTest, 20)
        other = self.store.get(Other, 300)

        obj.others.add(other)

        items = []
        for ref_obj in obj.others:
            items.append((ref_obj.id, ref_obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (100, "Title 300"),
                          (200, "Title 200"),
                          (300, "Title 100"),
                         ])

    def test_indirect_reference_set_remove(self):
        obj = self.store.get(IndRefSetTest, 20)
        other = self.store.get(Other, 200)

        obj.others.remove(other)

        items = []
        for ref_obj in obj.others:
            items.append((ref_obj.id, ref_obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (100, "Title 300"),
                         ])

    def test_indirect_reference_set_add_remove(self):
        obj = self.store.get(IndRefSetTest, 20)
        other = self.store.get(Other, 300)

        obj.others.add(other)
        obj.others.remove(other)

        items = []
        for ref_obj in obj.others:
            items.append((ref_obj.id, ref_obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (100, "Title 300"),
                          (200, "Title 200"),
                         ])

    def test_indirect_reference_set_add_remove_with_added(self):
        obj = IndRefSetTest()
        obj.id = 40
        other1 = Other()
        other1.id = 400
        other1.other_title = "Title 400"
        other2 = Other()
        other2.id = 500
        other2.other_title = "Title 500"
        self.store.add(obj)
        self.store.add(other1)
        self.store.add(other2)

        obj.others.add(other1)
        obj.others.add(other2)
        obj.others.remove(other1)

        items = []
        for ref_obj in obj.others:
            items.append((ref_obj.id, ref_obj.other_title))
        items.sort()

        self.assertEquals(items, [
                          (500, "Title 500"),
                         ])
        
    def test_flush_order(self):
        obj1 = Test()
        obj2 = Test()
        obj3 = Test()
        obj4 = Test()
        obj5 = Test()

        for i, obj in enumerate([obj1, obj2, obj3, obj4, obj5]):
            obj.title = "Object %d" % (i+1)
            self.store.add(obj)

        self.store.add_flush_order(obj2, obj4)
        self.store.add_flush_order(obj4, obj1)
        self.store.add_flush_order(obj1, obj3)
        self.store.add_flush_order(obj3, obj5)
        self.store.add_flush_order(obj5, obj2)
        self.store.add_flush_order(obj5, obj2)

        self.assertRaises(StoreError, self.store.flush)

        self.store.remove_flush_order(obj5, obj2)

        self.assertRaises(StoreError, self.store.flush)

        self.store.remove_flush_order(obj5, obj2)

        self.store.flush()

        self.assertTrue(obj2.id < obj4.id)
        self.assertTrue(obj4.id < obj1.id)
        self.assertTrue(obj1.id < obj3.id)
        self.assertTrue(obj3.id < obj5.id)

    def test_kind_filter_on_load(self):
        obj = self.store.get(KindTest, 20)
        self.assertEquals(obj.title, "to_py(from_db(Title 20))")

    def test_kind_filter_on_update(self):
        obj = self.store.get(KindTest, 20)
        obj.title = "Title 20"

        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "to_db(from_py(Title 20))"),
                          (30, "Title 10"),
                         ])

    def test_kind_filter_on_update_unchanged(self):
        obj = self.store.get(KindTest, 20)
        self.store.flush()
        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                         ])

    def test_kind_filter_on_insert(self):
        obj = KindTest()
        obj.id = 40
        obj.title = "Title 40"

        self.store.add(obj)
        self.store.flush()

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "Title 20"),
                          (30, "Title 10"),
                          (40, "to_db(from_py(Title 40))"),
                         ])

    def test_kind_filter_on_missing_values(self):
        obj = KindTest()
        obj.id = 40

        self.store.add(obj)
        self.store.flush()

        self.assertEquals(obj.title, "to_py(from_db(Default Title))")

    def test_kind_filter_on_set(self):
        obj = KindTest()
        self.store.find(KindTest, id=20).set(title="Title 20")

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "to_db(from_py(Title 20))"),
                          (30, "Title 10"),
                         ])

    def test_kind_filter_on_set_expr(self):
        obj = KindTest()
        self.store.find(KindTest, id=20).set(KindTest.title == "Title 20")

        self.assertEquals(self.get_items(), [
                          (10, "Title 30"),
                          (20, "to_db(from_py(Title 20))"),
                          (30, "Title 10"),
                         ])

    def test_wb_result_to_kind(self):
        def to_kind(self, value, kind):
            if kind.__class__ is StrKind:
                return "to_kind(%s)" % str(value)
            elif kind.__class__ is IntKind:
                return value+1
            return value

        result_factory = self.store._connection._result_factory
        old_to_kind, result_factory.to_kind = result_factory.to_kind, to_kind
        try:
            obj = self.store.get(Test, 20)
        finally:
            result_factory.to_kind = old_to_kind

        self.assertEquals(obj.id, 21)
        self.assertEquals(obj.title, "to_kind(Title 20)")
