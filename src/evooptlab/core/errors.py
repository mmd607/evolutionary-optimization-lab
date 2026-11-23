"""Exception hierarchy for the core interfaces."""

from __future__ import annotations


class EvoOptLabError(Exception):
    """Base class for all EvoOptLab errors."""


class ProblemDefinitionError(EvoOptLabError, ValueError):
    """A problem was defined with inconsistent dimensions or bounds."""


class CandidateError(EvoOptLabError, ValueError):
    """Candidate solutions have the wrong shape, are non-finite, or lie outside the bounds."""


class ObjectiveError(EvoOptLabError, RuntimeError):
    """A problem returned objective or constraint values of the wrong shape or non-finite."""


class BudgetExhaustedError(EvoOptLabError, RuntimeError):
    """An evaluation request would exceed the objective-evaluation budget."""


class AlgorithmError(EvoOptLabError, RuntimeError):
    """An algorithm violated the ask/tell contract (e.g. asked for zero candidates)."""
