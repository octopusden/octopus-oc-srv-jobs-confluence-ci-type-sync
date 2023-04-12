#!/usr/bin/env python3

import unittest
import unittest.mock
from oc_confluence_ci_type_sync.ci_types_sync import CiTypesSync
import argparse
import os
import json
import tempfile

# remove unnecessary log output
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True

class MockHttpException(Exception):
    def __init__(self, status_code):
        self.__status_code = status_code

    def __str__(self):
        return "Mock HTTP status error: %d" % self.__status_code

class MockHttpResponse():
    def __init__(self, status_code, json_ret=None, text_ret=None):
        self.status_code = status_code
        self.__json = json_ret
        self.text = text_ret

    def json(self):
        return self.__json

    def raise_for_status(self):
        if all([self.status_code >= 200,  self.status_code < 300]):
            return

        raise MockHttpException(self.status_code)

class OcConfluenceCiTypeSyncTest(unittest.TestCase):
    def test_initialization(self):
        _t = CiTypesSync()
        self.assertIsNone(_t._args)
        self.assertFalse(_t._orm_initialization_done)

    @property
    def __args(self):
        _result = unittest.mock.MagicMock()
        _result.psql_user = "test_user"
        _result.psql_password = "test_password"
        _result.psql_url = "psql_url"
        return _result

    def test_orm_initialization(self):
        _t = CiTypesSync()

        with unittest.mock.patch("oc_confluence_ci_type_sync.ci_types_sync.OrmInitializator") as _orm:
            with unittest.mock.patch('builtins.__import__') as _i:
                _t._args = self.__args
                self.assertIsInstance(_t._do_orm_initialization(), unittest.mock.MagicMock)
                _i.assert_called_once()
                _orm.assert_called_once_with(
                        url=_t._args.psql_url,
                        user=_t._args.psql_user,
                        password=_t._args.psql_password,
                        installed_apps=["oc_delivery_apps.checksums"])

    def test_basic_args(self):
        # the very-very-basic test becaus ArgumenParser is poorly documented - no evidence what to asserert
        _t = CiTypesSync()
        _a = _t.basic_args()
        self.assertIsInstance(_a, argparse.ArgumentParser)

    def test_get_citype_regexps(self):
        _t = CiTypesSync()
        _expected = ["the_reg_1", "the_reg_2", "the_reg_3"]
        _models = unittest.mock.MagicMock()
        _models.CiRegExp = unittest.mock.MagicMock()
        _models.CiRegExp.objects = unittest.mock.MagicMock()
        _rv = list()

        for _tt in _expected:
            _g = unittest.mock.MagicMock()
            _g.regexp=_tt
            _rv.append(_g)

        _models.CiRegExp.objects.filter = unittest.mock.MagicMock(return_value=_rv)
        _citype = unittest.mock.MagicMock()
        _citype.code="CI_CODE"

        _loctype = unittest.mock.MagicMock()
        _loctype.code = "LOC_CODE"
        _models.LocTypes = unittest.mock.MagicMock()
        _models.LocTypes.objects = unittest.mock.MagicMock()
        _models.LocTypes.objects.get = unittest.mock.MagicMock(return_value=_loctype)

        self.assertEqual(_t._get_citype_regexps(_models, _citype), _expected)
        _models.CiRegExp.objects.filter.assert_called_once_with(loc_type=_loctype, ci_type=_citype)


    def test_get_type_dict(self):
        _t = CiTypesSync()

        _models = unittest.mock.MagicMock()
        _citype = unittest.mock.MagicMock()
        _citype.code = "CI_CODE"
        _citype.name = "The Name"
        _citype.is_standard = "Y"
        _citype.is_deliverable = False
        _regexp = ["the_reg_1", "the_reg_2"]
        _t._get_citype_regexps = unittest.mock.MagicMock(return_value=_regexp)

        self.assertEqual(_t._get_type_dict(_models, _citype),
                {"code": _citype.code, "name": _citype.name, "standard": "Yes", "deliverable": "No", 
                    "regexp": _regexp, "rowspan": 1})
        _t._get_citype_regexps.assert_called_once_with(_models, _citype)

        # change a type
        _t._get_citype_regexps.reset_mock()
        _citype.is_standard = "N"
        _citype.is_deliverable = True
        self.assertEqual(_t._get_type_dict(_models, _citype),
                {"code": _citype.code, "name": _citype.name, "standard": "No", "deliverable": "Yes", 
                    "regexp": _regexp, "rowspan": 1})
        _t._get_citype_regexps.assert_called_once_with(_models, _citype)

    def test_get_group_rows(self):
        _t = CiTypesSync()

        _gr = {"types": []}

        self.assertEqual(_t._get_group_rows(_gr), 1)
        _gr["types"].append({"rowspan": 1})
        self.assertEqual(_t._get_group_rows(_gr), 1)
        _gr["types"].append({"rowspan": 1})
        self.assertEqual(_t._get_group_rows(_gr), 2)
        _gr["types"].append({"rowspan": 2})
        self.assertEqual(_t._get_group_rows(_gr), 4)
        _gr["types"] = [{"rowspan": 2}]
        self.assertEqual(_t._get_group_rows(_gr), 2)


    def test_get_citype_groups(self):
        _ts = CiTypesSync()

        # prepare test data
        _groups = list()

        # add 3 groups
        for _ig in range(0, 3):
            _g = unittest.mock.MagicMock()
            _g.code = "GROUP%d" % _ig
            _g.name = "Group %d" % _ig
            _groups.append(_g)

        _types = list()
        # add 9 types
        for _it in range(0, 9):
            _t = unittest.mock.MagicMock()
            _t.code = "TYPE%d" % _it
            _t.name = "Type %d" % _it
            _t.is_standard = "Y" if not _it % 2 else "N"
            _t.is_deliverable = bool(_it % 3)
            _types.append(_t)

        # include first 5 types to groups, last 4 - without group
        _incs = list()

        for _it in range(0, 5):
            _inc = unittest.mock.MagicMock()
            _inc.ci_type_group = _groups[_it if _it < len(_groups) else _it - len(_groups)]
            _inc.ci_type = _types[_it]
            _incs.append(_inc)

        # regexps are absent, so this field should be empty in result
        # getting regexps is tested in 'get_type_dict', no need to test it once again here

        class _Filterer():
            def __init__(self, **kwargs):
                self._result = list()
                self.call_count = 0

                for _inc in _incs:
                    _ok = True
                    for _k, _v in kwargs.items():
                        if getattr(_inc, _k) != _v:
                            _ok = False
                            break

                    if not _ok:
                        continue

                    self._result.append(_inc)

            def all(self):
                self.call_count += 1
                return self._result

            def count(self):
                return len(self._result)

        _models = unittest.mock.MagicMock()
        _models.CiTypeGroups = unittest.mock.MagicMock()
        _models.CiTypeGroups.objects = unittest.mock.MagicMock()
        _models.CiTypeGroups.objects.all = unittest.mock.MagicMock(return_value=_groups)

        _models.CiTypeIncs = unittest.mock.MagicMock()
        _models.CiTypeIncs.objects = unittest.mock.MagicMock()
        _models.CiTypeIncs.objects.filter = unittest.mock.MagicMock(side_effect=_Filterer)

        _models.CiTypes = unittest.mock.MagicMock()
        _models.CiTypes.objects = unittest.mock.MagicMock()
        _models.CiTypes.objects.all = unittest.mock.MagicMock(return_value=_types)

        # expected JSON
        _expected = [
                {'code': 'GROUP0', 'name': 'Group 0', 'types': [
                    {'code': 'TYPE0', 'name': 'Type 0', 'standard': 'Yes', 'deliverable': 'No', 'regexp': [], 'rowspan': 1},
                    {'code': 'TYPE3', 'name': 'Type 3', 'standard': 'No', 'deliverable': 'No', 'regexp': [], 'rowspan': 1}
                    ], 'rowspan': 2},
                {'code': 'GROUP1', 'name': 'Group 1', 'types': [
                    {'code': 'TYPE1', 'name': 'Type 1', 'standard': 'No', 'deliverable': 'Yes', 'regexp': [], 'rowspan': 1},
                    {'code': 'TYPE4', 'name': 'Type 4', 'standard': 'Yes', 'deliverable': 'Yes', 'regexp': [], 'rowspan': 1}
                    ], 'rowspan': 2},
                {'code': 'GROUP2', 'name': 'Group 2', 'types': [
                    {'code': 'TYPE2', 'name': 'Type 2', 'standard': 'Yes', 'deliverable': 'Yes', 'regexp': [], 'rowspan': 1}
                    ], 'rowspan': 1},
                {'code': '', 'name': '', 'types': [
                    {'code': 'TYPE5', 'name': 'Type 5', 'standard': 'No', 'deliverable': 'Yes', 'regexp': [], 'rowspan': 1},
                    {'code': 'TYPE6', 'name': 'Type 6', 'standard': 'Yes', 'deliverable': 'No', 'regexp': [], 'rowspan': 1},
                    {'code': 'TYPE7', 'name': 'Type 7', 'standard': 'No', 'deliverable': 'Yes', 'regexp': [], 'rowspan': 1},
                    {'code': 'TYPE8', 'name': 'Type 8', 'standard': 'Yes', 'deliverable': 'Yes', 'regexp': [], 'rowspan': 1}
                    ], 'rowspan': 4}]

        self.assertEqual(_expected, _ts._get_citype_groups(_models))

        # assert mocks
        _models.CiTypeGroups.objects.all.assert_called_once()
        self.assertEqual(_models.CiTypeIncs.objects.filter.call_count, len(_groups) + len(_types))

        for _g in _groups:
            _models.CiTypeIncs.objects.filter.assert_any_call(ci_type_group=_g)

        for _t in _types:
            _models.CiTypeIncs.objects.filter.assert_any_call(ci_type=_t)

        _models.CiTypes.objects.all.assert_called_once()

    def test_render_template(self):
        # simple test for rendering template given
        _ts = CiTypesSync()
        _ts._args = unittest.mock.MagicMock()
        _templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data", "render_template")
        _ts._args.page_template = os.path.join(_templates_dir, "test.html.template")

        with open(os.path.join(_templates_dir, "test_data.json"), mode='rt') as _f:
            _context = json.load(_f)

        with open(os.path.join(_templates_dir, "result.html"), mode='rt') as _r:
            # note about 'strip()': some text editors do add extra newline character at the end of file when preparing the expected render result
            # while Jinja does not. Stripping those newline is essential then
            self.assertEqual(_r.read().strip(), _ts._render_template(_context).strip())

    def test_make_context(self):
        # we add some env variables only
        _report = "group_report_stub"
        _ts = CiTypesSync()
        _ts._args = unittest.mock.MagicMock()
        _ts._args.mvn_prefix = "prefix"
        self.assertEqual({"mvn_prefix": "prefix", "groups": "group_report_stub"}, _ts._make_context(_report))

    def test_get_confluence_page_id(self):
        _ts = CiTypesSync()
        _ts._args = unittest.mock.MagicMock()
        _ts._args.wiki_url = "https://confluence.example.com"
        _ts._args.wiki_user = "test_user"
        _ts._args.wiki_password = "test_password"
        _ts._args.page_title = "Test Page 3"

        with self.assertRaises(MockHttpException):
            with unittest.mock.patch("requests.get") as _rqp:
                _rqp.return_value = MockHttpResponse(403)
                _ts._get_confluence_page_id()

        with unittest.mock.patch("requests.get") as _rqp:
            _rqp.return_value = MockHttpResponse(200, json_ret={"results": [{"id":12}]})

            self.assertEqual(12, _ts._get_confluence_page_id())

            _rqp.assert_called_once_with("https://confluence.example.com/rest/api/content",
                    params={"title": "Test Page 3"},
                    headers={"Content-type": "application/json"},
                    auth=("test_user", "test_password"))

    def test_get_page_current_content(self):
        _ts = CiTypesSync()
        _ts._args = unittest.mock.MagicMock()
        _ts._args.wiki_url = "https://confluence.example.com"
        _ts._args.wiki_user = "test_user"
        _ts._args.wiki_password = "test_password"
        _ts._args.page_title = "Test Page 3"

        with unittest.mock.patch("requests.get") as _rqp:

            with self.assertRaises(MockHttpException):
                _rqp.return_value = MockHttpResponse(403)
                _ts._get_page_current_content("12")

            _rqp.reset_mock()
            _rqp.return_value = MockHttpResponse(200, json_ret={"content": "test_content"})
            self.assertEqual({"content": "test_content"}, _ts._get_page_current_content("12"))

            _rqp.assert_called_once_with("https://confluence.example.com/rest/api/content/12",
                    params={"expand": "body.storage"},
                    headers={"Content-type": "application/json"},
                    auth=("test_user", "test_password"))

    def test_get_page_new_version(self):
        _ts = CiTypesSync()
        _ts._args = unittest.mock.MagicMock()
        _ts._args.wiki_url = "https://confluence.example.com"
        _ts._args.wiki_user = "test_user"
        _ts._args.wiki_password = "test_password"
        _ts._args.page_title = "Test Page 3"

        with unittest.mock.patch("requests.get") as _rqp:
            with self.assertRaises(MockHttpException):
                _rqp.return_value = MockHttpResponse(403)
                _ts._get_page_new_version("12")

            _rqp.reset_mock()
            _rqp.return_value = MockHttpResponse(200, json_ret={"version": {"number": "10"}})
            self.assertEqual("11", _ts._get_page_new_version("12"))

            _rqp.assert_called_once_with("https://confluence.example.com/rest/api/content/12",
                    params={"expand": "version.number"},
                    headers={"Content-type": "application/json"},
                    auth=("test_user", "test_password"))

    def test_make_new_page_object(self):
        _ts = CiTypesSync()

        _current = {
                "id": "10",
                "type": "test_type",
                "title": "Test Page 4",
                "status": "current",
                "body": {"storage": {"value": "test_body_previous", "representation": "repro", "extra": "test_extra_should_be_removed"}, "extra": "test_extra_should_be_purged"},
                "version": {"number": "9", "extra": "version_extra_to_be_assasinated"},
                "extra": "test_extra_should_be_deleted" 
                }
        _expected = {
                "id": "10",
                "type": "test_type",
                "title": "Test Page 4",
                "status": "current",
                "body": {"storage": {"value": "current_test_body", "representation": "storage"}},
                "version": {"number": "10"},
                }

        self.assertEqual(_ts._make_new_page_object(_current, "10", "current_test_body"), _expected)

    def test_put_to_confluence(self):
        _ts = CiTypesSync()
        _ts._args = unittest.mock.MagicMock()
        _ts._args.wiki_url = "https://confluence.example.com"
        _ts._args.wiki_user = "test_user"
        _ts._args.wiki_password = "test_password"
        _ts._args.page_title = "Test Page 3"

        with unittest.mock.patch("requests.put") as _rqp:
            with self.assertRaises(MockHttpException):
                _rqp.return_value = MockHttpResponse(403)
                _ts._put_to_confluence("12", {"content": "the content"})

            _rqp.reset_mock()
            _rqp.return_value = MockHttpResponse(200, json_ret={}, text_ret="The text")
            _ts._put_to_confluence("12", {"content": "the content"})

            _rqp.assert_called_once_with("https://confluence.example.com/rest/api/content/12",
                    headers={"Content-type": "application/json"},
                    auth=("test_user", "test_password"),
                    data=json.dumps({"content": "the content"}))

    def test_save_report(self):
        _ts = CiTypesSync()
        _ts._args = unittest.mock.MagicMock()
        _ts._get_confluence_page_id = unittest.mock.MagicMock(return_value="1")
        _ts._get_page_current_content = unittest.mock.MagicMock(return_value="the_content")
        _ts._get_page_new_version = unittest.mock.MagicMock(return_value="2")
        _ts._make_new_page_object = unittest.mock.MagicMock(return_value="the object")
        _ts._put_to_confluence = unittest.mock.MagicMock()

        # write to file
        _out = tempfile.NamedTemporaryFile()
        _ts._args.fn_out = _out.name
        _ts._save_report("report string")

        with open(_out.name, mode='rt') as _t:
            self.assertEqual(_t.read(), "report string")

        _out.close()
        _ts._get_confluence_page_id.assert_not_called()
        _ts._get_page_current_content.assert_not_called()
        _ts._get_page_new_version.assert_not_called()
        _ts._make_new_page_object.assert_not_called()
        _ts._put_to_confluence.assert_not_called()

        # put to server
        _ts._args.fn_out = None
        _ts._args.page_title = "Test Page"
        _ts._save_report("report string")
        _ts._get_confluence_page_id.assert_called_once()
        _ts._get_page_current_content.assert_called_once_with("1")
        _ts._get_page_new_version.assert_called_once_with("1")
        _ts._make_new_page_object.assert_called_once_with("the_content", "2", "report string")
        _ts._put_to_confluence.assert_called_once_with("1", "the object")


    def test_run(self):
        _ts = CiTypesSync()
        _args = unittest.mock.MagicMock()
        _args.page_template = "the_page.template"

        _models = unittest.mock.MagicMock()
        _ts._do_orm_initialization = unittest.mock.MagicMock(return_value=_models)
        _ts._get_citype_groups = unittest.mock.MagicMock(return_value="the_report")
        _ts._make_context = unittest.mock.MagicMock(return_value="the_context")
        _ts._render_template = unittest.mock.MagicMock(return_value="the_rendered_template")
        _ts._save_report = unittest.mock.MagicMock()

        _ts.run(_args)
        self.assertEqual(_ts._args, _args)
        self.assertEqual(_ts._args.page_template, os.path.abspath("the_page.template"))

        _ts._do_orm_initialization.assert_called_once()
        _ts._get_citype_groups.assert_called_once_with(_models)
        _ts._make_context.assert_called_once_with("the_report")
        _ts._render_template.assert_called_once_with("the_context")
        _ts._save_report.assert_called_once_with("the_rendered_template")
