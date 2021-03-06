import unittest

from jobgraph.util import python_path


class TestObject:

    testClassProperty = object()


class TestPythonPath(unittest.TestCase):
    def test_find_object_no_such_module(self):
        """find_object raises ImportError for a nonexistent module"""
        self.assertRaises(
            ImportError, python_path.find_object, "no_such_module:someobj"
        )

    def test_find_object_no_such_object(self):
        """find_object raises AttributeError for a nonexistent object"""
        self.assertRaises(
            AttributeError,
            python_path.find_object,
            "jobgraph.test.test_util_python_path:NoSuchObject",
        )

    def test_find_object_exists(self):
        """find_object finds an existing object"""
        from jobgraph.test.test_util_python_path import TestObject

        obj = python_path.find_object(
            "jobgraph.test.test_util_python_path:TestObject.testClassProperty"
        )
        self.assertIs(obj, TestObject.testClassProperty)
