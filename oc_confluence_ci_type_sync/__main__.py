#!/usr/bin/env python3
from .ci_types_sync import CiTypesSync

_synchronizer = CiTypesSync()
_parser = _synchronizer.basic_args()
_args = _parser.parse_args()
_synchronizer.run(_args)
