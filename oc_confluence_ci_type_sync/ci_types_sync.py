#!/usr/bin/env python3

import argparse
import logging
import os
from urllib.parse import urljoin
from oc_orm_initializator.orm_initializator import OrmInitializator
import jinja2
import pkg_resources
import posixpath
import requests
from copy import copy
import json

class CiTypesSync:
    def __init__(self):
        """
        Main class initialization
        """
        self._args = None
        self._orm_initialization_done = False

    def _do_orm_initialization(self):
        """
        Do Django ORM initalization
        """
        _installed_apps = ["oc_delivery_apps.checksums"]

        OrmInitializator(
            url=self._args.psql_url,
            user=self._args.psql_user,
            password=self._args.psql_password,
            installed_apps=_installed_apps)

        from oc_delivery_apps.checksums import models

        return models


    def basic_args(self, parser=None):
        """
        Get parser with basic arguments
        :return ArgumentParser: ArgumentParser instance with basic arguments added
        """
        if not parser:
            parser = argparse.ArgumentParser(description = "CI_TYPES report for CONFLUENCE export")

        parser.add_argument("--psql-url", dest="psql_url", help="PSQL URL, including schema path", 
                default=os.getenv("PSQL_URL"))
        parser.add_argument("--psql-user", dest="psql_user", help="PSQL user",
                default=os.getenv("PSQL_USER"))
        parser.add_argument("--psql-password", dest="psql_password", help="PSQL password",
                default=os.getenv("PSQL_PASSWORD"))
        parser.add_argument("--wiki-url", dest="wiki_url", help="Confluence (WIKI) URL, including schema path", 
                default=os.getenv("WIKI_URL"))
        parser.add_argument("--wiki-user", dest="wiki_user", help="Confluence (WIKI) user",
                default=os.getenv("WIKI_USER"))
        parser.add_argument("--wiki-password", dest="wiki_password", help="Confluence (WIKI) password",
                default=os.getenv("WIKI_PASSWORD"))
        parser.add_argument("--mvn-prefix", dest="mvn_prefix", help="MVN prefix for groupId of maven artifacts",
                default=os.getenv("MVN_PREFIX"))
        parser.add_argument("--page-title", dest="page_title", help="Confluence (WIKI) page title to replace",
                default="CI_TYPE_GROUPS and CI_TYPES")
        parser.add_argument("--page-template", dest="page_template", 
                help="Path to Jinja2 template for resulting page",
                default=pkg_resources.resource_filename("oc_confluence_ci_type_sync",
                    os.path.join("templates", "ci-type-groups-and-ci-types.xhtml.template")))
        parser.add_argument("--log-level", dest="log_level", help = "Log level", type=int, default=20)
        parser.add_argument("--out", dest="fn_out", 
                help="Write output to local file specified here, do not put to Confluence", type=str)

        return parser

    def _get_citype_regexps(self, models, citype):
        """
        Return a (possible empty) list of regular expressions assigned to type.
        :param django.Models models: database models
        :param checksums.CiType citype: CiType object to get regexps for
        :return list: list of strings with regular expressions
        """
        _locType = models.LocTypes.objects.get(code="NXS")
        _result = list()
        
        # doing so because we do not need a failure in case of no expressions
        for _regexp in models.CiRegExp.objects.filter(loc_type=_locType, ci_type=citype):
            if not _regexp.regexp:
                continue

            _result.append(_regexp.regexp)

        logging.debug("Found '%d' regexps for type '%s'" % (len(_result), citype.code))

        return _result

    def _get_type_dict(self, models, citype):
        """
        Return a type dictionary for further output
        :param django.Models models: database models
        :param checksums.CiType citype: CiType object to get regexps for
        :return dict: type-related dictionary
        """
        logging.debug("Processing type: '%s'" % citype.code)
        _type_dict = {
                    "code": citype.code,
                    "name": citype.name,
                    "standard": "Yes" if citype.is_standard == "Y" else "No",
                    "deliverable": "Yes" if citype.is_deliverable else "No",
                    "regexp": self._get_citype_regexps(models, citype)}

        _type_dict["rowspan"] = 1 
        # previous revision: len(_type_dict.get("regexp", list())) or 1
        logging.debug("Rows for type '%s': '%d'" % (_type_dict.get("code"), _type_dict.get("rowspan")))

        return _type_dict

    def _get_group_rows(self, group_dict):
        """
        Return a number of table rows necessary to fill group information into a table
        :param dict group_dict: group dictionary
        :return int: number of rows
        """
        logging.debug("Counting group rows for '%s'" % group_dict.get("code"))
        if not group_dict.get("types"):
            # at least one row is necessary even for empty group
            logging.debug("No members in '%s', returning 1" % group_dict.get("code"))
            return 1

        _rows = 0
        
        for _type in group_dict.get("types"):
            _rows += _type.get("rowspan", 1)

        logging.debug("Returning '%d' rows for group '%s'" % (_rows, group_dict.get("code")))
        return _rows

    def _get_citype_groups(self, models):
        """
        Get JSON-ed report for groups and types from DB
        :param django.model models: django models
        :return list: report
        """
        _result = list()

        # see groupped types first
        for _cigroup in models.CiTypeGroups.objects.all():
            _group_dict = {"code": _cigroup.code, "name": _cigroup.name, "types": list()}

            # append individual types
            for _inc in models.CiTypeIncs.objects.filter(ci_type_group=_cigroup).all():
                _citype = _inc.ci_type
                _type_dict = self._get_type_dict(models, _citype) 

                _group_dict["types"].append(_type_dict)

            _group_dict["rowspan"] = self._get_group_rows(_group_dict)

            _result.append(_group_dict)

        # append non-groupped types
        _group_dict = {"code": "", "name": "", "types": list()}

        for _citype in models.CiTypes.objects.all():
            # if there is any inclusion into group - skip this type
            if models.CiTypeIncs.objects.filter(ci_type=_citype).count():
                continue

            _type_dict = self._get_type_dict(models, _citype)
            _group_dict["types"].append(_type_dict)

        _group_dict["rowspan"] = self._get_group_rows(_group_dict)
        _result.append(_group_dict)

        return _result

    def _render_template(self, report):
        """
        Render Jinja2-template with report
        :param list report: ci-type-groups report
        :return str: rendered template
        """
        _loader = jinja2.FileSystemLoader(os.path.dirname(self._args.page_template))
        _env = jinja2.Environment(loader=_loader)
        _template = _env.get_template(os.path.basename(self._args.page_template))
        _report = _template.render(report)

        return _report

    def _make_context(self, report):
        """
        Return context for template rendering
        :return dict: context for rendering
        """
        return {"mvn_prefix": self._args.mvn_prefix, "groups": report}

    def _get_confluence_page_id(self):
        """
        Return page_id for conluence
        """
        _rq_url = urljoin(self._args.wiki_url, posixpath.join("rest", "api", "content"))
        logging.debug("RQ URL: '%s'" % _rq_url)
        _rq_parms = {"title": self._args.page_title}
        _headers = {"Content-type": "application/json"}
        _resp = requests.get(_rq_url, params=_rq_parms, headers=_headers,
                auth=(self._args.wiki_user, self._args.wiki_password))

        if _resp.status_code < 200  or _resp.status_code >= 300:
            _resp.raise_for_status()

        _page_id=_resp.json().get("results").pop(0).get("id")
        logging.info("Page '%s' id: %s" % (_rq_parms.get("title"), _page_id))
        return _page_id

    def _get_page_current_content(self, page_id):
        """
        Get current page content by id
        :param str page_id: confluence page_id
        :return dict:
        """
        _rq_url = urljoin(self._args. wiki_url, posixpath.join("rest", "api", "content", page_id))
        logging.debug("RQ URL: '%s'" % _rq_url)
        _rq_parms = {"expand": "body.storage"}
        _headers = {"Content-type": "application/json"}
        _resp = requests.get(_rq_url, params=_rq_parms, headers=_headers,
                auth=(self._args.wiki_user, self._args.wiki_password))

        if _resp.status_code < 200  or _resp.status_code >= 300:
            _resp.raise_for_status()

        return _resp.json()

    def _get_page_new_version(self, page_id):
        """
        Return current page version from Confluence
        :param str page_id: Confluence page id
        :return str: current page version
        """
        _rq_url = urljoin(self._args. wiki_url, posixpath.join("rest", "api", "content", page_id))
        logging.debug("RQ URL: '%s'" % _rq_url)
        _rq_parms = {"expand": "version.number"}
        _headers = {"Content-type": "application/json"}
        _resp = requests.get(_rq_url, params=_rq_parms, headers=_headers,
                auth=(self._args.wiki_user, self._args.wiki_password))

        if _resp.status_code < 200  or _resp.status_code >= 300:
            _resp.raise_for_status()

        _version = _resp.json().get("version").get("number")
        _version = str(int(_version) + 1)
        logging.info("New version number: %s" % _version)
        return _version

    def _make_new_page_object(self, current_content, new_version, new_content):
        """
        Construct dict (JSONized) page object to put to Confluence
        :param dict current_content: current page object from Confluence
        :param str new_version: new page version
        :param str new_content: new page content, XHTML, without metadata
        """

        _keys_n = ['id', 'type', 'title', 'status', 'body', 'version']
        _keys_p = copy(list(current_content.keys()))
        _keys_p = list(filter(lambda x: x not in _keys_n, _keys_p))

        for _k in _keys_p:
            del(current_content[_k])

        _keys_n = ['storage']
        _keys_p = copy(list(current_content.get('body').keys()))
        _keys_p = list(filter(lambda x: x not in _keys_n, _keys_p))

        for _k in _keys_p:
            del(current_content['body'][_k])

        _keys_n = ['value', 'representation']
        _keys_p = copy(list(current_content.get('body').get('storage').keys()))
        _keys_p = list(filter(lambda x: x not in _keys_n, _keys_p))

        for _k in _keys_p:
            del(current_content['body']['storage'][_k])

        current_content['body']['storage'] = {"value": new_content, "representation": "storage"}
        current_content['version'] = {'number': new_version}

        return current_content

    def _put_to_confluence(self, page_id, page_content):
        """
        Save new page version to Confluence
        :param str page_id: Confluence page_id to overwrite
        :param dict page_content: new JSONed page content, with metadata
        """
        _rq_url = urljoin(self._args. wiki_url, posixpath.join("rest", "api", "content", page_id))
        logging.debug("RQ URL: '%s'" % _rq_url)
        _headers = {"Content-type": "application/json"}
        _resp = requests.put(_rq_url, headers=_headers, 
                auth=(self._args.wiki_user, self._args.wiki_password), data=json.dumps(page_content))
        logging.info("Page '%s' put status code: '%d'" % (page_id, _resp.status_code))
        logging.debug(_resp.text)

        if _resp.status_code < 200  or _resp.status_code >= 300:
            _resp.raise_for_status()

    def _save_report(self, report):
        """
        Put rendered report to Confluence
        :param str report: rendered XHTML report suitable for Confluence
        """
        if self._args.fn_out:
            _fn_out = os.path.abspath(self._args.fn_out)
            logging.info("Writing rendered template to: '%s'" % _fn_out)
            with open(_fn_out, mode="wt") as _fl_out:
                _fl_out.write(report)

            return

        _page_id = self._get_confluence_page_id()
        _content = self._get_page_current_content(_page_id)
        _version = self._get_page_new_version(_page_id)
        _page_object = self._make_new_page_object(_content, _version, report)
        self._put_to_confluence(_page_id, _page_object)

    def run(self, args):
        """
        Main run process
        :param namespace args: parsed command-line arguments
        """
        self._args = args
        self._args.page_template = os.path.abspath(self._args.page_template)

        # logger configuration
        logging.basicConfig(
                format="%(pathname)s: %(asctime)-15s: %(levelname)s: %(funcName)s: %(lineno)d: %(message)s",
                level=self._args.log_level)

        logging.info("Logging level is set to %d" % self._args.log_level)
        logging.info("PSQL URL: '%s'" % self._args.psql_url)
        logging.info("PSQL user: '%s'" % self._args.psql_user)
        logging.info("PSQL password: %s" % ('***' if self._args.psql_password else 'NOT SET'))

        logging.info("WIKI URL: '%s'" % self._args.wiki_url)
        logging.info("WIKI user: '%s'" % self._args.wiki_user)
        logging.info("WIKI password: %s" % ('***' if self._args.wiki_password else 'NOT SET'))

        logging.info("MVN prefix: '%s'" % self._args.mvn_prefix)
        logging.info("Page title: '%s'" % self._args.page_title)
        logging.info("Template: '%s'" % self._args.page_template)

        _models = self._do_orm_initialization()
        _json_group_report = self._get_citype_groups(_models)
        _rendered_template = self._render_template(self._make_context(_json_group_report))
        self._save_report(_rendered_template)

