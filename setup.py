#!/usr/bin/env python3
from setuptools import setup
import glob
import os

VERSION="0.0.0.6"

def list_recursive(app, directory, extension="*"):
    dir_to_walk = os.path.join(app, directory)

    found = [result for (cur_dir, subdirs, files) in os.walk(dir_to_walk)
             for result in glob.glob(os.path.join(cur_dir, '*.' + extension))]

    found_in_package = list(map(lambda x: x.replace(app + os.path.sep, "", 1), found))
    return found_in_package


_spec = {
    'name': "oc_confluence_ci_type_sync",
    'version': VERSION,
    'description': 'Replace ci-types report at Confluence page',
    'packages': ['oc_confluence_ci_type_sync'],
    'install_requires': [
        "oc-orm-initializator",
        "oc-delivery-apps",
        "Jinja2",
        "requests"
    ],
    "package_data": {
        "oc_confluence_ci_type_sync": list_recursive("oc_confluence_ci_type_sync", "templates")
    },
    "python_requires": ">=3.7"
}

setup(**_spec)
