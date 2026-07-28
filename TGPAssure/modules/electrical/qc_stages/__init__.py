"""Electrical QC stage namespace.

The production stage orchestration currently lives in :mod:`modules.electrical.qc_engine`
so all stages share one immutable dataset/result contract. This package is reserved for
future instrument- or client-specific stage extensions without changing public APIs.
"""
