"""AgentSeed guard engine — path setup hub + re-export from engine/ package.

This module is the single entry point that sets up ``sys.path`` so that
``engine/`` can be imported from any working directory. All entry-point
scripts (server, CLI, tests) import through this module instead of
duplicating the ``sys.path.insert(0, ...)`` boilerplate.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import *  # noqa: E402, F401, F403