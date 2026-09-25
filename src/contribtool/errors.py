class ContribToolError(Exception):
    """Expected, user-facing error."""

class GitError(ContribToolError):
    pass

class ValidationError(ContribToolError):
    pass
