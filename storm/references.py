#
# Copyright (c) 2006 Canonical
#
# Written by Gustavo Niemeyer <gustavo@niemeyer.net>
#
# This file is part of Storm Object Relational Mapper.
#
# <license text goes here>
#
from storm.exceptions import WrongStoreError, NoStoreError
from storm.store import Store, get_where_for_args
from storm.expr import Select, Exists, Undef, compare_columns
from storm.info import *


class Reference(object):

    def __init__(self, local_key, remote_key, on_remote=False):
        self._relation = Relation(local_key, remote_key, False, on_remote)

    def __get__(self, local, cls=None):
        if local is None:
            return self

        remote = self._relation.get_remote(local)
        if remote is not None:
            return remote

        store = Store.of(local)
        if store is None:
            return None

        if self._relation.remote_key_is_primary:
            remote = store.get(self._relation.remote_cls,
                               self._relation.get_local_variables(local))
        else:
            where = self._relation.get_where_for_remote(local)
            remote = store.find(self._relation.remote_cls, where).one()

        if remote is not None:
            self._relation.link(local, remote)

        return remote

    def __set__(self, local, remote):
        if remote is None:
            remote = self._relation.get_remote(local)
            if remote is not None:
                self._relation.unlink(local, remote, True)
        else:
            self._relation.link(local, remote, True)


class ReferenceSet(object):

    def __init__(self, local_key1, remote_key1,
                 remote_key2=None, local_key2=None, order_by=None):
        self._relation1 = Relation(local_key1, remote_key1, True, True)
        if local_key2 and remote_key2:
            self._relation2 = Relation(local_key2, remote_key2, True, True)
        else:
            self._relation2 = None
        self._order_by = order_by

    def __get__(self, local, cls=None):
        if local is None:
            return self
        #store = Store.of(local)
        #if store is None:
        #    return None
        if self._relation2 is None:
            return BoundReferenceSet(self._relation1, local, self._order_by)
        else:
            return BoundIndirectReferenceSet(self._relation1,
                                             self._relation2, local,
                                             self._order_by)


class BoundReferenceSet(object):

    def __init__(self, relation, local, order_by):
        self._relation = relation
        self._local = local
        self._target_cls = self._relation.remote_cls
        self._order_by = order_by

    def __iter__(self):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = self._relation.get_where_for_remote(self._local)
        result = store.find(self._target_cls, where)
        if self._order_by is not None:
            result = result.order_by(self._order_by)
        return result.__iter__()

    def find(self, *args, **kwargs):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = self._relation.get_where_for_remote(self._local)
        result = store.find(self._target_cls, where, *args, **kwargs)
        if self._order_by is not None:
            return result.order_by(self._order_by)
        return result

    def first(self, *args, **kwargs):
        return self.find(*args, **kwargs).first()

    def last(self, *args, **kwargs):
        return self.find(*args, **kwargs).last()

    def any(self, *args, **kwargs):
        return self.find(*args, **kwargs).any()

    def values(self, *columns):
        return self.find().values(*columns)

    def order_by(self, *args):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = self._relation.get_where_for_remote(self._local)
        return store.find(self._target_cls, where).order_by(*args)

    def count(self):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = self._relation.get_where_for_remote(self._local)
        return store.find(self._target_cls, where).count()

    def clear(self, *args, **kwargs):
        set_kwargs = {}
        for remote_column in self._relation.remote_key:
            set_kwargs[remote_column.name] = None
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = self._relation.get_where_for_remote(self._local)
        store.find(self._target_cls, where, *args, **kwargs).set(**set_kwargs)

    def add(self, remote):
        self._relation.link(self._local, remote, True)

    def remove(self, remote):
        self._relation.unlink(self._local, remote, True)


class BoundIndirectReferenceSet(object):

    def __init__(self, relation1, relation2, local, order_by):
        self._relation1 = relation1
        self._relation2 = relation2
        self._local = local
        self._order_by = order_by

        self._target_cls = relation2.local_cls
        self._link_cls = relation1.remote_cls

    def __iter__(self):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = (self._relation1.get_where_for_remote(self._local) &
                 self._relation2.get_where_for_join())
        result = store.find(self._target_cls, where)
        if self._order_by is not None:
            result = result.order_by(self._order_by)
        return result.__iter__()

    def find(self, *args, **kwargs):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = (self._relation1.get_where_for_remote(self._local) &
                 self._relation2.get_where_for_join())
        result = store.find(self._target_cls, where, *args, **kwargs)
        if self._order_by is not None:
            return result.order_by(self._order_by)
        return result

    def first(self, *args, **kwargs):
        return self.find(*args, **kwargs).first()

    def last(self, *args, **kwargs):
        return self.find(*args, **kwargs).last()

    def any(self, *args, **kwargs):
        return self.find(*args, **kwargs).any()

    def values(self, *columns):
        return self.find().values(*columns)

    def order_by(self, *args):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = (self._relation1.get_where_for_remote(self._local) &
                 self._relation2.get_where_for_join())
        return store.find(self._target_cls, where).order_by(*args)

    def count(self):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = (self._relation1.get_where_for_remote(self._local) &
                 self._relation2.get_where_for_join())
        return store.find(self._target_cls, where).count()

    def clear(self, *args, **kwargs):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = self._relation1.get_where_for_remote(self._local)
        if args or kwargs:
            filter = get_where_for_args(self._target_cls, args, kwargs)
            join = self._relation2.get_where_for_join()
            table = get_cls_info(self._target_cls).table
            where &= Exists(Select("*", join & filter, tables=table))
        store.find(self._link_cls, where).remove()

    def add(self, remote):
        link = self._link_cls()
        self._relation1.link(self._local, link, True)
        self._relation2.link(remote, link, True)

    def remove(self, remote):
        store = Store.of(self._local)
        if store is None:
            raise NoStoreError("Can't perform operation without a store")
        where = (self._relation1.get_where_for_remote(self._local) &
                 self._relation2.get_where_for_remote(remote))
        store.find(self._link_cls, where).remove()


class Relation(object):

    def __init__(self, local_key, remote_key, many, on_remote):
        if type(local_key) is tuple:
            self.local_key = local_key
        else:
            self.local_key = (local_key,)
        if type(remote_key) is tuple:
            self.remote_key = remote_key
        else:
            self.remote_key = (remote_key,)

        self.local_cls = getattr(self.local_key[0], "cls", None)
        self.remote_cls = self.remote_key[0].cls
        self.remote_key_is_primary = False

        primary_key = get_cls_info(self.remote_cls).primary_key
        if len(primary_key) == len(self.remote_key):
            for column1, column2 in zip(self.remote_key, primary_key):
                if column1.name != column2.name:
                    break
            else:
                self.remote_key_is_primary = True

        self.many = many
        self.on_remote = on_remote

        self._local_columns = {}

        self._l_to_r = {}
        self._r_to_l = {}

    def get_remote(self, local):
        remote_info = get_obj_info(local).get(self)
        if remote_info is not None:
            return remote_info.obj
        return None

    def get_where_for_remote(self, local):
        local_variables = self.get_local_variables(local)
        for variable in local_variables:
            if not variable.is_defined():
                Store.of(local).flush()
                break
        return compare_columns(self.remote_key, local_variables)

    def get_where_for_join(self):
        return compare_columns(self.local_key, self.remote_key)

    def get_local_variables(self, local):
        local_info = get_obj_info(local)
        return tuple(local_info.variables[column]
                     for column in self._get_local_columns(local.__class__))

    def link(self, local, remote, setting=False):
        local_info = get_obj_info(local)
        remote_info = get_obj_info(remote)

        local_store = Store.of(local)
        remote_store = Store.of(remote)

        if local_store is None:
            if remote_store is None:
                local_info.event.hook("added", self._add_all, local_info)
                remote_info.event.hook("added", self._add_all, local_info)
            else:
                remote_store.add(local)
                local_store = remote_store
        elif remote_store is None:
            local_store.add(remote)
        elif local_store is not remote_store:
            raise WrongStoreError("Objects are living in different stores")

        if self.many:
            relations = local_info.get(self)
            if relations is None:
                local_info[self] = set((remote_info,))
            else:
                relations.add(remote_info)
        else:
            old_remote_info = local_info.get(self)
            if old_remote_info is not None:
                self.unlink(local, old_remote_info.obj)
            local_info[self] = remote_info

        if setting:
            local_vars = local_info.variables
            remote_vars = remote_info.variables
            pairs = zip(self._get_local_columns(local.__class__),
                        self.remote_key)
            if self.on_remote:
                for local_column, remote_column in pairs:
                    local_var = local_vars[local_column]
                    if not local_var.is_defined():
                        track_changes = True
                    else:
                        remote_vars[remote_column].set(local_var.get())

                if local_store is not None:
                    local_store.add_flush_order(local, remote)

                local_info.event.hook("changed", self._track_local_changes,
                                      remote_info)
                local_info.event.hook("flushed", self._break_on_local_flushed,
                                      remote_info)
                #local_info.event.hook("removed", self._break_on_local_removed,
                #                      remote_info)
            else:
                for local_column, remote_column in pairs:
                    remote_var = remote_vars[remote_column]
                    if not remote_var.is_defined():
                        track_changes = True
                    else:
                        local_vars[local_column].set(remote_var.get())

                if local_store is not None:
                    local_store.add_flush_order(remote, local)

                remote_info.event.hook("changed", self._track_remote_changes,
                                       local_info)
                remote_info.event.hook("flushed", self._break_on_remote_flushed,
                                       local_info)
                #local_info.event.hook("removed", self._break_on_remote_removed,
                #                      local_info)

                local_info.event.hook("changed", self._break_on_local_diverged,
                                      remote_info)
        else:
            local_info.event.hook("changed", self._break_on_local_diverged,
                                  remote_info)
            remote_info.event.hook("changed", self._break_on_remote_diverged,
                                   local_info)

    def unlink(self, local, remote, setting=False):

        local_info = get_obj_info(local)
        remote_info = get_obj_info(remote)

        unhook = False
        if self.many:
            relations = local_info.get(self)
            if relations is not None and remote_info in relations:
                relations.discard(remote_info)
                unhook = True
        elif local_info.pop(self, None) is not None:
            unhook = True
        
        if unhook:
            local_store = Store.of(local)

            local_info.event.unhook("changed", self._track_local_changes,
                                    remote_info)
            local_info.event.unhook("changed", self._break_on_local_diverged,
                                    remote_info)
            local_info.event.unhook("flushed", self._break_on_local_flushed,
                                    remote_info)

            remote_info.event.unhook("changed", self._track_remote_changes,
                                     local_info)
            remote_info.event.unhook("changed", self._break_on_remote_diverged,
                                     local_info)
            remote_info.event.unhook("flushed", self._break_on_remote_flushed,
                                     local_info)

            if local_store is None:
                if not self.many or not relations:
                    local_info.event.unhook("added", self._add_all, local_info)
                remote_info.event.unhook("added", self._add_all, local_info)

            if local_store is not None:
                if self.on_remote:
                    local_store.remove_flush_order(local, remote)
                else:
                    local_store.remove_flush_order(remote, local)

        if setting:
            if self.on_remote:
                remote_vars = remote_info.variables
                for remote_column in self.remote_key:
                    remote_vars[remote_column].set(None)
            else:
                local_vars = local_info.variables
                for local_column in self._get_local_columns(local.__class__):
                    local_vars[local_column].set(None)

    def _track_local_changes(self, local_info, local_variable,
                             old_value, new_value, remote_info):
        """Deliver changes in local to remote.

        This hook ensures that the remote object will keep track of
        changes done in the local object, either manually or at
        flushing time.
        """
        remote_column = self._get_remote_column(local_info.obj.__class__,
                                                local_variable.column)
        if remote_column is not None:
            remote_info.variables[remote_column].set(new_value)

    def _track_remote_changes(self, remote_info, remote_variable,
                              old_value, new_value, local_info):
        """Deliver changes in remote to local.

        This hook ensures that the local object will keep track of
        changes done in the remote object, either manually or at
        flushing time.
        """
        local = local_info.obj
        local_column = self._get_local_column(local.__class__,
                                              remote_variable.column)
        if local_column is not None:
            local_info.variables[local_column].set(new_value)

    def _break_on_local_diverged(self, local_info, local_variable,
                                 old_value, new_value, remote_info):
        """Break the remote/local relationship on diverging changes.

        This hook ensures that if the local object has an attribute
        changed by hand in a way that diverges from the remote object,
        it stops tracking changes.
        """
        local = local_info.obj
        remote_column = self._get_remote_column(local.__class__,
                                                local_variable.column)
        if remote_column is not None:
            remote_value = remote_info.variables[remote_column].get()
            if remote_value != new_value:
                self.unlink(local, remote_info.obj)

    def _break_on_remote_diverged(self, remote_info, remote_variable,
                                  old_value, new_value, local_info):
        """Break the remote/local relationship on diverging changes.

        This hook ensures that if the remote object has an attribute
        changed by hand in a way that diverges from the local object,
        the relationship is undone.
        """
        local = local_info.obj
        local_column = self._get_local_column(local.__class__,
                                              remote_variable.column)
        if local_column is not None:
            local_value = get_obj_info(local).variables[local_column].get()
            if local_value != new_value:
                self.unlink(local, remote_info.obj)

    def _break_on_local_flushed(self, local_info, remote_info):
        """Break the remote/local relationship on flush."""
        self.unlink(local_info.obj, remote_info.obj)

    def _break_on_remote_flushed(self, remote_info, local_info):
        """Break the remote/local relationship on flush."""
        self.unlink(local_info.obj, remote_info.obj)

    def _add_all(self, obj_info, local_info):
        local = local_info.obj
        store = Store.of(obj_info.obj)
        store.add(local)
        local_info.event.unhook("added", self._add_all, local_info)

        def add(remote_info):
            remote_info.event.unhook("added", self._add_all,
                                              local_info)
            remote = remote_info.obj
            store.add(remote)
            if self.on_remote:
                store.add_flush_order(local, remote)
            else:
                store.add_flush_order(remote, local)

        if self.many:
            for remote_info in local_info[self]:
                add(remote_info)
        else:
            add(local_info[self])

    def _get_local_columns(self, local_cls):
        try:
            return self._local_columns[local_cls]
        except KeyError:
            columns = [prop.__get__(None, local_cls)
                       for prop in self.local_key]
            self._local_columns[local_cls] = columns
            return columns

    def _get_remote_column(self, local_cls, local_column):
        try:
            return self._l_to_r[local_cls].get(local_column)
        except KeyError:
            map = {}
            for local_prop, _remote_column in zip(self.local_key,
                                                   self.remote_key):
                map[local_prop.__get__(None, local_cls)] = _remote_column
            return self._l_to_r.setdefault(local_cls, map).get(local_column)

    def _get_local_column(self, local_cls, remote_column):
        try:
            return self._r_to_l[local_cls].get(remote_column)
        except KeyError:
            map = {}
            for local_prop, _remote_column in zip(self.local_key,
                                                   self.remote_key):
                map[_remote_column] = local_prop.__get__(None, local_cls)
            return self._r_to_l.setdefault(local_cls, map).get(remote_column)

