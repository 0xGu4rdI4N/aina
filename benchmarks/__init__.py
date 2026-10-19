"""
benchmarks — Standardized Evaluation & Domain Reasoning Suites for aina
======================================================================
Implements:
1. Razavi Domain Reasoning Benchmark (Verifiable Qualitative & Analytical Circuit Physics)
2. LOADBench / AutoCkt Two-Stage Miller OTA Sizing Benchmark
"""

from .razavi_reasoning import (
    RazaviBenchmark,
    RazaviQuestion,
    evaluate_reasoning_response,
    get_default_razavi_suite,
)
from .two_stage_ota import (
    TwoStageOTABenchmark,
    OTASpecification,
    DEFAULT_NOMINAL_OTA_PARAMS,
)

__all__ = [
    "RazaviBenchmark",
    "RazaviQuestion",
    "evaluate_reasoning_response",
    "get_default_razavi_suite",
    "TwoStageOTABenchmark",
    "OTASpecification",
    "DEFAULT_NOMINAL_OTA_PARAMS",
]
